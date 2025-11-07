#!/usr/bin/env python3
"""
Import knowledge base collections from JSON export files.

Usage:
    # Dry-run (validation only)
    python import_collections.py --file export.json --target-env production --dry-run

    # Actual import
    python import_collections.py --file export.json --target-env production

    # Generate new UUIDs instead of preserving original
    python import_collections.py --file export.json --target-env production --new-uuids
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

from .config import ConfigError, load_config
from .user_mapper import UserMapper, UserMappingError, create_user_mapper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ImportError(Exception):
    """Import-related errors."""
    pass


class CollectionImporter:
    """Import collections with user ID mapping and transaction safety."""

    def __init__(
        self,
        conn_params: Dict[str, Any],
        user_mapper: UserMapper,
        preserve_uuids: bool = True
    ):
        """
        Initialize importer.

        Args:
            conn_params: Database connection parameters
            user_mapper: UserMapper for translating user IDs
            preserve_uuids: Whether to preserve original UUIDs or generate new ones
        """
        self.conn_params = conn_params
        self.user_mapper = user_mapper
        self.preserve_uuids = preserve_uuids

        # Track what we've created for rollback
        self.created_collections = []

    def get_connection(self):
        """Create database connection."""
        return psycopg2.connect(**self.conn_params)

    def collection_exists(self, collection_id: UUID) -> bool:
        """Check if a collection with this UUID already exists."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM langconnect.langchain_pg_collection
                    WHERE uuid = %s
                """, (str(collection_id),))
                return cur.fetchone() is not None

    def collection_name_exists(self, name: str) -> Optional[UUID]:
        """Check if a collection with this name exists. Returns UUID if found."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT uuid FROM langconnect.langchain_pg_collection
                    WHERE name = %s
                """, (name,))
                result = cur.fetchone()
                return result[0] if result else None

    def import_collection(
        self,
        collection_data: Dict[str, Any],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Import a single collection with all related data.

        Args:
            collection_data: Collection export data
            dry_run: If True, validate but don't make changes

        Returns:
            Import result dict with status and details
        """
        collection = collection_data["collection"]
        documents = collection_data["documents"]
        embeddings = collection_data["embeddings"]
        permissions = collection_data["permissions"]

        source_collection_id = UUID(collection["uuid"])
        collection_name = collection["name"]

        logger.info(f"Importing collection: {collection_name}")

        # Determine target collection UUID
        if self.preserve_uuids:
            target_collection_id = source_collection_id
            # Check if it already exists
            if self.collection_exists(target_collection_id):
                return {
                    "status": "error",
                    "collection_name": collection_name,
                    "source_id": str(source_collection_id),
                    "error": "Collection UUID already exists in target environment"
                }
        else:
            # Check if name already exists
            existing_id = self.collection_name_exists(collection_name)
            if existing_id:
                return {
                    "status": "error",
                    "collection_name": collection_name,
                    "source_id": str(source_collection_id),
                    "error": f"Collection name already exists (UUID: {existing_id})"
                }
            target_collection_id = uuid4()

        logger.info(f"  Target UUID: {target_collection_id}")
        logger.info(f"  Documents: {len(documents)}")
        logger.info(f"  Embeddings: {len(embeddings)}")
        logger.info(f"  Permissions: {len(permissions)}")

        # Map permissions
        try:
            mapped_permissions = self.user_mapper.map_permissions(permissions)
            logger.info(f"  Mapped permissions: {len(mapped_permissions)}")
        except UserMappingError as e:
            return {
                "status": "error",
                "collection_name": collection_name,
                "source_id": str(source_collection_id),
                "error": f"User mapping failed: {e}"
            }

        if dry_run:
            return {
                "status": "dry_run_ok",
                "collection_name": collection_name,
                "source_id": str(source_collection_id),
                "target_id": str(target_collection_id),
                "documents": len(documents),
                "embeddings": len(embeddings),
                "permissions": len(mapped_permissions)
            }

        # Actual import - use transaction
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Create collection
                    cur.execute("""
                        INSERT INTO langconnect.langchain_pg_collection (uuid, name, cmetadata)
                        VALUES (%s, %s, %s)
                    """, (
                        str(target_collection_id),
                        collection_name,
                        json.dumps(collection["cmetadata"])
                    ))

                    self.created_collections.append(target_collection_id)

                    # 2. Import documents (build ID mapping)
                    document_id_mapping = {}
                    for doc in documents:
                        source_doc_id = UUID(doc["id"])
                        target_doc_id = uuid4() if not self.preserve_uuids else source_doc_id

                        cur.execute("""
                            INSERT INTO langconnect.langchain_pg_document
                            (id, collection_id, content, cmetadata)
                            VALUES (%s, %s, %s, %s)
                        """, (
                            str(target_doc_id),
                            str(target_collection_id),
                            doc["content"],
                            json.dumps(doc["cmetadata"])
                        ))

                        document_id_mapping[str(source_doc_id)] = str(target_doc_id)

                    # 3. Import embeddings (bulk insert for performance)
                    if embeddings:
                        embedding_rows = []
                        for emb in embeddings:
                            # Map document_id
                            source_doc_id = emb.get("document_id")
                            target_doc_id = document_id_mapping.get(str(source_doc_id)) if source_doc_id else None

                            # Preserve or generate new embedding ID
                            source_emb_id = emb["id"]
                            target_emb_id = source_emb_id if self.preserve_uuids else f"{target_collection_id}:{uuid4()}"

                            embedding_rows.append((
                                target_emb_id,
                                str(target_collection_id),
                                str(target_doc_id) if target_doc_id else None,
                                emb["content"],
                                emb["embedding_vector"],
                                json.dumps(emb["cmetadata"])
                            ))

                        # Bulk insert embeddings
                        execute_values(
                            cur,
                            """
                            INSERT INTO langconnect.langchain_pg_embedding
                            (id, collection_id, document_id, document, embedding, cmetadata)
                            VALUES %s
                            """,
                            embedding_rows,
                            template="(%s, %s, %s, %s, %s::vector, %s)"
                        )

                    # 4. Create permissions
                    for perm in mapped_permissions:
                        cur.execute("""
                            INSERT INTO langconnect.collection_permissions
                            (collection_id, user_id, permission_level, granted_by)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (collection_id, user_id) DO UPDATE
                            SET permission_level = EXCLUDED.permission_level,
                                granted_by = EXCLUDED.granted_by,
                                updated_at = NOW()
                        """, (
                            str(target_collection_id),
                            perm["user_id"],
                            perm["permission_level"],
                            perm.get("granted_by", "system:import")
                        ))

                    conn.commit()

            return {
                "status": "success",
                "collection_name": collection_name,
                "source_id": str(source_collection_id),
                "target_id": str(target_collection_id),
                "documents_imported": len(documents),
                "embeddings_imported": len(embeddings),
                "permissions_created": len(mapped_permissions)
            }

        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            return {
                "status": "error",
                "collection_name": collection_name,
                "source_id": str(source_collection_id),
                "error": str(e)
            }


def load_export_bundle(file_path: Path) -> Dict[str, Any]:
    """Load and validate export bundle."""
    if not file_path.exists():
        raise ImportError(f"Export file not found: {file_path}")

    try:
        with open(file_path, "r") as f:
            bundle = json.load(f)
    except json.JSONDecodeError as e:
        raise ImportError(f"Invalid JSON in export file: {e}")

    # Validate bundle structure
    required_keys = ["export_metadata", "collections"]
    for key in required_keys:
        if key not in bundle:
            raise ImportError(f"Invalid export bundle: missing '{key}'")

    metadata = bundle["export_metadata"]
    if metadata.get("format") != "collection_export":
        raise ImportError(f"Unsupported export format: {metadata.get('format')}")

    if metadata.get("version") != "1.0":
        logger.warning(f"Export version {metadata.get('version')} may not be fully supported")

    return bundle


def main():
    parser = argparse.ArgumentParser(
        description="Import knowledge base collections from JSON export",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run validation
  %(prog)s --file export.json --target-env production --dry-run

  # Import with original UUIDs
  %(prog)s --file export.json --target-env production

  # Import with new UUIDs (safer if source still exists)
  %(prog)s --file export.json --target-env production --new-uuids
        """
    )

    # Required arguments
    parser.add_argument(
        "--file",
        "-f",
        type=Path,
        required=True,
        help="Path to export JSON file"
    )
    parser.add_argument(
        "--target-env",
        type=str,
        help="Target environment name (e.g., 'production')"
    )

    # Options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only, don't make changes"
    )
    parser.add_argument(
        "--new-uuids",
        action="store_true",
        help="Generate new UUIDs instead of preserving original (recommended if source still exists)"
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        help="Path to config directory (default: database/transfer_configs)"
    )

    args = parser.parse_args()

    try:
        # Load configuration
        config = load_config(args.config_dir)

        # Load export bundle
        logger.info(f"Loading export file: {args.file}")
        bundle = load_export_bundle(args.file)

        metadata = bundle["export_metadata"]
        collections = bundle["collections"]

        logger.info(f"Export metadata:")
        logger.info(f"  Source environment: {metadata['source_environment']}")
        logger.info(f"  Exported at: {metadata['exported_at']}")
        logger.info(f"  Collections: {metadata['collection_count']}")

        # Determine target environment
        target_env = args.target_env or config.get_default_target()
        source_env = metadata["source_environment"]

        logger.info(f"Target environment: {target_env}")

        if args.dry_run:
            logger.info("🔍 DRY RUN MODE - No changes will be made")

        # Get target connection parameters
        target_conn_params = config.get_connection_params(target_env)

        # Create user mapper
        user_mapper = create_user_mapper(config, source_env, target_env, target_conn_params)

        # Show mapping report
        mapping_report = user_mapper.get_mapping_report()
        logger.info(f"User mapping configuration:")
        logger.info(f"  Target users found: {mapping_report['target_users_count']}")
        logger.info(f"  Explicit mappings: {mapping_report['explicit_mappings_count']}")
        logger.info(f"  Default owner: {mapping_report['default_owner']}")

        # Create importer
        importer = CollectionImporter(
            target_conn_params,
            user_mapper,
            preserve_uuids=not args.new_uuids
        )

        # Import each collection
        results = []
        for coll_data in collections:
            result = importer.import_collection(coll_data, dry_run=args.dry_run)
            results.append(result)

        # Summary
        success_count = sum(1 for r in results if r["status"] in ["success", "dry_run_ok"])
        error_count = sum(1 for r in results if r["status"] == "error")

        print("\n" + "="*60)
        print("IMPORT SUMMARY")
        print("="*60)

        for result in results:
            status_symbol = "✅" if result["status"] in ["success", "dry_run_ok"] else "❌"
            print(f"{status_symbol} {result['collection_name']}")

            if result["status"] in ["success", "dry_run_ok"]:
                print(f"   Source ID: {result['source_id']}")
                print(f"   Target ID: {result['target_id']}")
                print(f"   Documents: {result.get('documents_imported', result.get('documents', 0))}")
                print(f"   Embeddings: {result.get('embeddings_imported', result.get('embeddings', 0))}")
                print(f"   Permissions: {result.get('permissions_created', result.get('permissions', 0))}")
            else:
                print(f"   Error: {result['error']}")
            print()

        print(f"Total: {success_count} successful, {error_count} failed")

        if args.dry_run:
            print("\n✅ Dry-run validation complete. Use without --dry-run to perform actual import.")
        elif error_count == 0:
            print("\n✅ Import complete!")
        else:
            print("\n⚠️  Import completed with errors")
            sys.exit(1)

    except (ConfigError, ImportError, UserMappingError) as e:
        logger.error(f"Import failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
