#!/usr/bin/env python3
"""
Export knowledge base collections to portable JSON format.

Usage:
    # Export single collection by UUID
    python export_collections.py --collection-id UUID --source-env local

    # Export single collection by name
    python export_collections.py --collection-name "My Collection" --source-env local

    # Export all collections
    python export_collections.py --all --source-env local

    # Skip embeddings for faster export
    python export_collections.py --collection-name "Test" --no-embeddings
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import ConfigError, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CollectionExporter:
    """Export collections with all related data to JSON format."""

    def __init__(self, conn_params: Dict[str, Any]):
        """Initialize exporter with database connection parameters."""
        self.conn_params = conn_params

    def get_connection(self):
        """Create database connection."""
        return psycopg2.connect(**self.conn_params)

    def get_collection_by_id(self, collection_id: UUID) -> Optional[Dict]:
        """Fetch collection metadata by UUID."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        uuid,
                        name,
                        cmetadata,
                        created_at,
                        updated_at
                    FROM langconnect.langchain_pg_collection
                    WHERE uuid = %s
                """, (collection_id,))
                result = cur.fetchone()
                return dict(result) if result else None

    def get_collection_by_name(self, name: str) -> Optional[Dict]:
        """Fetch collection metadata by name."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        uuid,
                        name,
                        cmetadata,
                        created_at,
                        updated_at
                    FROM langconnect.langchain_pg_collection
                    WHERE name = %s
                    LIMIT 1
                """, (name,))
                result = cur.fetchone()
                return dict(result) if result else None

    def get_all_collections(self) -> List[Dict]:
        """Fetch all non-system collections."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        uuid,
                        name,
                        cmetadata,
                        created_at,
                        updated_at
                    FROM langconnect.langchain_pg_collection
                    WHERE uuid != '00000000-0000-0000-0000-000000000001'::uuid  -- Exclude system collection
                    ORDER BY created_at
                """)
                return [dict(row) for row in cur.fetchall()]

    def get_documents(self, collection_id: UUID) -> List[Dict]:
        """Fetch all documents in a collection."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        id,
                        content,
                        cmetadata,
                        created_at,
                        updated_at
                    FROM langconnect.langchain_pg_document
                    WHERE collection_id = %s
                    ORDER BY created_at
                """, (collection_id,))
                return [dict(row) for row in cur.fetchall()]

    def get_embeddings(self, collection_id: UUID) -> List[Dict]:
        """Fetch all embeddings in a collection."""
        logger.info(f"  Fetching embeddings (this may take a while for large collections)...")
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        id,
                        document_id,
                        document as content,
                        embedding::text as embedding_vector,
                        cmetadata,
                        created_at,
                        updated_at
                    FROM langconnect.langchain_pg_embedding
                    WHERE collection_id = %s
                    ORDER BY created_at
                """, (collection_id,))
                return [dict(row) for row in cur.fetchall()]

    def get_permissions(self, collection_id: UUID) -> List[Dict]:
        """Fetch all permissions for a collection."""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        cp.user_id,
                        cp.permission_level,
                        cp.granted_by,
                        ur.email,
                        ur.display_name,
                        ur.role
                    FROM langconnect.collection_permissions cp
                    LEFT JOIN langconnect.user_roles ur ON cp.user_id = ur.user_id
                    WHERE cp.collection_id = %s
                """, (collection_id,))
                return [dict(row) for row in cur.fetchall()]

    def export_collection(
        self,
        collection_id: UUID,
        include_embeddings: bool = True
    ) -> Dict:
        """Export a single collection with all related data."""
        logger.info(f"Exporting collection {collection_id}...")

        # Get collection metadata
        collection = self.get_collection_by_id(collection_id)
        if not collection:
            raise ValueError(f"Collection {collection_id} not found")

        logger.info(f"  Collection: {collection['name']}")

        # Get documents
        documents = self.get_documents(collection_id)
        logger.info(f"  Documents: {len(documents)}")

        # Get embeddings (optional, can be large)
        embeddings = []
        if include_embeddings:
            embeddings = self.get_embeddings(collection_id)
            logger.info(f"  Embeddings: {len(embeddings)}")
        else:
            logger.info(f"  Embeddings: skipped (use --include-embeddings to export)")

        # Get permissions
        permissions = self.get_permissions(collection_id)
        logger.info(f"  Permissions: {len(permissions)}")

        return {
            "collection": collection,
            "documents": documents,
            "embeddings": embeddings,
            "permissions": permissions,
            "stats": {
                "document_count": len(documents),
                "embedding_count": len(embeddings),
                "permission_count": len(permissions),
                "embeddings_included": include_embeddings
            }
        }

    def create_export_bundle(
        self,
        collections_data: List[Dict],
        source_environment: str
    ) -> Dict:
        """Create a complete export bundle with metadata."""
        # Extract all unique users from permissions
        unique_users = {}
        for coll_data in collections_data:
            for perm in coll_data["permissions"]:
                user_id = perm["user_id"]
                if user_id not in unique_users:
                    unique_users[user_id] = {
                        "email": perm.get("email"),
                        "display_name": perm.get("display_name"),
                        "role": perm.get("role")
                    }

        return {
            "export_metadata": {
                "version": "1.0",
                "format": "collection_export",
                "source_environment": source_environment,
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "collection_count": len(collections_data)
            },
            "user_directory": unique_users,
            "collections": collections_data
        }


def serialize_json(obj):
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def main():
    parser = argparse.ArgumentParser(
        description="Export knowledge base collections to JSON format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export single collection by name
  %(prog)s --collection-name "My Collection" --source-env local -o export.json

  # Export all collections
  %(prog)s --all --source-env production -o all_collections.json

  # Export without embeddings (faster, smaller)
  %(prog)s --collection-name "Test" --no-embeddings -o test.json
        """
    )

    # Collection selection (mutually exclusive)
    collection_group = parser.add_mutually_exclusive_group(required=True)
    collection_group.add_argument(
        "--collection-id",
        type=str,
        help="UUID of collection to export"
    )
    collection_group.add_argument(
        "--collection-name",
        type=str,
        help="Name of collection to export"
    )
    collection_group.add_argument(
        "--all",
        action="store_true",
        help="Export all non-system collections"
    )

    # Environment
    parser.add_argument(
        "--source-env",
        type=str,
        help="Source environment name (e.g., 'local', 'production'). Required unless --config-dir is used with defaults."
    )

    # Output
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output JSON file path (default: exports/collection_YYYYMMDD_HHMMSS.json)"
    )

    # Options
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Skip embeddings (faster export, smaller file size)"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output (more readable but larger file)"
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

        # Determine source environment
        source_env = args.source_env or config.get_default_source()
        logger.info(f"Source environment: {source_env}")

        # Get connection parameters
        conn_params = config.get_connection_params(source_env)

        # Initialize exporter
        exporter = CollectionExporter(conn_params)

        # Determine which collections to export
        collections_to_export = []

        if args.collection_id:
            collection = exporter.get_collection_by_id(UUID(args.collection_id))
            if not collection:
                logger.error(f"Collection {args.collection_id} not found")
                sys.exit(1)
            collections_to_export = [collection]

        elif args.collection_name:
            collection = exporter.get_collection_by_name(args.collection_name)
            if not collection:
                logger.error(f"Collection '{args.collection_name}' not found")
                sys.exit(1)
            collections_to_export = [collection]

        elif args.all:
            collections_to_export = exporter.get_all_collections()
            if not collections_to_export:
                logger.warning("No collections found to export")
                sys.exit(0)
            logger.info(f"Found {len(collections_to_export)} collections to export")

        # Export each collection
        collections_data = []
        for collection in collections_to_export:
            collection_data = exporter.export_collection(
                collection["uuid"],
                include_embeddings=not args.no_embeddings
            )
            collections_data.append(collection_data)

        # Create export bundle
        bundle = exporter.create_export_bundle(
            collections_data,
            source_environment=source_env
        )

        # Determine output path
        if args.output:
            output_path = args.output
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path("database/exports") / f"collection_{timestamp}.json"

        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            if args.pretty:
                json.dump(bundle, f, indent=2, default=serialize_json)
            else:
                json.dump(bundle, f, default=serialize_json)

        # Summary
        file_size_mb = output_path.stat().st_size / 1024 / 1024
        logger.info("✅ Export complete!")
        logger.info(f"   Output file: {output_path}")
        logger.info(f"   Collections: {len(collections_data)}")
        logger.info(f"   Total documents: {sum(c['stats']['document_count'] for c in collections_data)}")
        logger.info(f"   Total embeddings: {sum(c['stats']['embedding_count'] for c in collections_data)}")
        logger.info(f"   File size: {file_size_mb:.2f} MB")

    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
