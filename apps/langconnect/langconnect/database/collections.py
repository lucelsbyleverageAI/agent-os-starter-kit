"""Module defines CollectionManager and Collection classes.

1. CollectionManager: for managing collections of documents in a database.
2. Collection: for managing the contents of a specific collection.
3. CollectionPermissionsManager: for managing collection sharing permissions.

The current implementations are based on langchain-postgres PGVector class.

Replace with your own implementation or favorite vectorstore if needed.
"""

import builtins
import json
import logging
import re
import uuid
from typing_extensions import TypedDict
from typing import Any, NotRequired, Optional, List

from fastapi import status
from fastapi.exceptions import HTTPException
from langchain_core.documents import Document

from langconnect.database.connection import get_db_connection, get_vectorstore
from langconnect.database.document import DocumentManager
from langconnect.models import PermissionLevel

logger = logging.getLogger(__name__)


class CollectionDetails(TypedDict):
    """TypedDict for collection details."""

    uuid: str
    name: str
    metadata: dict[str, Any]
    permission_level: NotRequired[str]
    # Temporary field used internally to workaround an issue with PGVector
    table_id: NotRequired[str]


class CollectionPermissionsManager:
    """Manager for collection sharing permissions."""

    def __init__(self, user_id: str) -> None:
        """Initialize the permissions manager with a user ID."""
        self.user_id = user_id

    async def grant_permission(
        self,
        collection_id: str,
        target_user_id: str,
        permission_level: PermissionLevel,
    ) -> bool:
        """Grant permission to a user for a collection."""
        async with get_db_connection() as conn:
            # Service accounts have admin access - skip permission checks
            if not (hasattr(self, '_is_service_account') and self._is_service_account):
                # First verify the granting user has owner permission or owns the collection
                has_permission = await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM collection_permissions 
                        WHERE collection_id = $1 AND user_id = $2 AND permission_level = 'owner'
                    ) OR EXISTS(
                        SELECT 1 FROM langchain_pg_collection 
                        WHERE uuid = $1 AND cmetadata->>'owner_id' = $2
                    )
                    """,
                    collection_id,
                    self.user_id,
                )

                if not has_permission:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You don't have permission to share this collection",
                    )

            # Insert or update permission
            await conn.execute(
                """
                INSERT INTO collection_permissions (collection_id, user_id, permission_level, granted_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (collection_id, user_id) 
                DO UPDATE SET 
                    permission_level = EXCLUDED.permission_level,
                    granted_by = EXCLUDED.granted_by,
                    updated_at = NOW()
                """,
                collection_id,
                target_user_id,
                permission_level.value,
                self.user_id,
            )

            return True

    async def revoke_permission(self, collection_id: str, target_user_id: str) -> bool:
        """Revoke permission from a user for a collection."""
        async with get_db_connection() as conn:
            # Service accounts have admin access - skip permission checks
            if not (hasattr(self, '_is_service_account') and self._is_service_account):
                # Verify the revoking user has owner permission
                has_permission = await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM collection_permissions 
                        WHERE collection_id = $1 AND user_id = $2 AND permission_level = 'owner'
                    ) OR EXISTS(
                        SELECT 1 FROM langchain_pg_collection 
                        WHERE uuid = $1 AND cmetadata->>'owner_id' = $2
                    )
                    """,
                    collection_id,
                    self.user_id,
                )

                if not has_permission:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You don't have permission to revoke access to this collection",
                    )

            # Don't allow removing owner permissions
            existing_permission = await conn.fetchval(
                """
                SELECT permission_level FROM collection_permissions
                WHERE collection_id = $1 AND user_id = $2
                """,
                collection_id,
                target_user_id,
            )

            if existing_permission == "owner":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot revoke owner permissions",
                )

            result = await conn.execute(
                """
                DELETE FROM collection_permissions 
                WHERE collection_id = $1 AND user_id = $2 AND permission_level != 'owner'
                """,
                collection_id,
                target_user_id,
            )

            return int(result.split()[-1]) > 0

    async def list_collection_permissions(self, collection_id: str) -> List[dict[str, Any]]:
        """List all permissions for a collection."""
        async with get_db_connection() as conn:
            # Service accounts have admin access - skip permission checks
            if not (hasattr(self, '_is_service_account') and self._is_service_account):
                # Verify user has access to this collection
                has_access = await self._user_has_collection_access(collection_id)
                if not has_access:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You don't have access to this collection",
                    )

            rows = await conn.fetch(
                """
                SELECT id, collection_id, user_id, permission_level, granted_by, created_at, updated_at
                FROM collection_permissions
                WHERE collection_id = $1
                ORDER BY created_at DESC
                """,
                collection_id,
            )

            return [
                {
                    "id": str(row["id"]),
                    "collection_id": str(row["collection_id"]),
                    "user_id": row["user_id"],
                    "permission_level": row["permission_level"],
                    "granted_by": row["granted_by"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    async def _user_has_collection_access(self, collection_id: str) -> bool:
        """Check if user has any access to a collection."""
        async with get_db_connection() as conn:
            return await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM collection_permissions 
                    WHERE collection_id = $1 AND user_id = $2
                ) OR EXISTS(
                    SELECT 1 FROM langchain_pg_collection 
                    WHERE uuid = $1 AND cmetadata->>'owner_id' = $2
                )
                """,
                collection_id,
                self.user_id,
            )

    async def get_user_permission_level(self, collection_id: str) -> str | None:
        """Get the user's permission level for a collection."""
        # Service accounts have admin access to all collections
        if hasattr(self, '_is_service_account') and self._is_service_account:
            return "owner"
            
        async with get_db_connection() as conn:
            # Check explicit permissions first
            permission = await conn.fetchval(
                """
                SELECT permission_level FROM collection_permissions
                WHERE collection_id = $1 AND user_id = $2
                """,
                collection_id,
                self.user_id,
            )

            if permission:
                return permission

            # Check if user is the original owner (legacy)
            is_owner = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM langchain_pg_collection 
                    WHERE uuid = $1 AND cmetadata->>'owner_id' = $2
                )
                """,
                collection_id,
                self.user_id,
            )

            return "owner" if is_owner else None


class CollectionsManager:
    """Use to create, delete, update, and list document collections."""

    def __init__(self, user_id: str) -> None:
        """Initialize the collection manager with a user ID."""
        self.user_id = user_id
        self.permissions_manager = CollectionPermissionsManager(user_id)

    @staticmethod
    async def setup() -> None:
        """Set up method should run any necessary initialization code.

        For example, it could run SQL migrations to create the necessary tables.
        """
        logger.info("Starting database initialization...")
        get_vectorstore()
        logger.info("Database initialization complete.")

    async def list(
        self,
    ) -> list[CollectionDetails]:
        """List all collections accessible by the given user, ordered by logical name."""
        async with get_db_connection() as conn:
            # Check if this is a service account (admin access)
            if hasattr(self, '_is_service_account') and self._is_service_account:
                # Service accounts have admin access to all collections
                records = await conn.fetch(
                    """
                    SELECT c.uuid, c.cmetadata, 'owner' as permission_level
                    FROM langchain_pg_collection c
                    ORDER BY c.cmetadata->>'name'
                    """
                )
            else:
                # Regular user access - check permissions
                records = await conn.fetch(
                    """
                    WITH user_collections AS (
                        -- Get all collections the user has access to
                        SELECT DISTINCT c.uuid
                        FROM langchain_pg_collection c
                        LEFT JOIN collection_permissions p ON c.uuid = p.collection_id AND p.user_id = $1
                        WHERE p.user_id = $1 OR c.cmetadata->>'owner_id' = $1
                    ),
                    user_permissions AS (
                        -- Get the highest permission level for each collection
                        SELECT collection_id, MAX(permission_level) as permission_level
                        FROM collection_permissions
                        WHERE user_id = $1
                        GROUP BY collection_id
                    )
                    SELECT c.uuid, c.cmetadata,
                           COALESCE(up.permission_level, 'owner') as permission_level
                    FROM langchain_pg_collection c
                    JOIN user_collections uc ON c.uuid = uc.uuid
                    LEFT JOIN user_permissions up ON c.uuid = up.collection_id
                    ORDER BY c.cmetadata->>'name'
                    """,
                    self.user_id,
                )

        result: list[CollectionDetails] = []
        for r in records:
            cmetadata = r["cmetadata"]
            if cmetadata is not None:
                try:
                    metadata = json.loads(cmetadata)
                    # Ensure metadata is a dict (json.loads can return None in some edge cases)
                    if not isinstance(metadata, dict):
                        metadata = {}
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse cmetadata for collection {r['uuid']}: {cmetadata}, error: {e}")
                    metadata = {}
            else:
                metadata = {}
            
            name = metadata.pop("name", "Unnamed")
            result.append(
                {
                    "uuid": str(r["uuid"]),
                    "name": name,
                    "metadata": metadata,
                    "permission_level": r["permission_level"],
                }
            )
        return result

    async def get(
        self,
        collection_id: str,
    ) -> CollectionDetails | None:
        """Fetch a single collection by UUID, ensuring the user has access to it."""
        async with get_db_connection() as conn:
            # Check if this is a service account (admin access)
            # Service accounts can access any collection
            if hasattr(self, '_is_service_account') and self._is_service_account:
                # Admin access - get collection without permission checks
                rec = await conn.fetchrow(
                    """
                    SELECT c.uuid, c.name, c.cmetadata, 'owner' as permission_level
                    FROM langchain_pg_collection c
                    WHERE c.uuid = $1
                    """,
                    collection_id,
                )
            else:
                # Regular user access - check permissions
                rec = await conn.fetchrow(
                    """
                    SELECT c.uuid, c.name, c.cmetadata,
                           COALESCE(p.permission_level, 'owner') as permission_level
                    FROM langchain_pg_collection c
                    LEFT JOIN collection_permissions p ON c.uuid = p.collection_id AND p.user_id = $2
                    WHERE c.uuid = $1 
                      AND (p.user_id = $2 OR c.cmetadata->>'owner_id' = $2)
                    """,
                    collection_id,
                    self.user_id,
                )

        if not rec:
            return None

        cmetadata = rec["cmetadata"]
        if cmetadata is not None:
            try:
                metadata = json.loads(cmetadata)
                # Ensure metadata is a dict (json.loads can return None in some edge cases)
                if not isinstance(metadata, dict):
                    metadata = {}
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse cmetadata for collection {collection_id}: {cmetadata}")
                metadata = {}
        else:
            metadata = {}
        name = metadata.pop("name", "Unnamed")
        return {
            "uuid": str(rec["uuid"]),
            "name": name,
            "metadata": metadata,
            "permission_level": rec["permission_level"],
            "table_id": rec["name"],
        }

    async def create(
        self,
        collection_name: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CollectionDetails | None:
        """Create a new collection.

        Args:
            collection_name: The name of the new collection.
            metadata: Optional metadata for the collection.

        Returns:
            Details of the created collection or None if creation failed.
        """
        # check for existing name
        metadata = metadata.copy() if metadata else {}
        metadata["owner_id"] = self.user_id
        metadata["name"] = collection_name

        # Create a meaningful table name from collection name + UUID for uniqueness
        # This ensures the internal table name is more readable while staying unique
        # Sanitize collection name for use in table name (keep alphanumeric and underscores)
        sanitized_name = re.sub(r'[^a-zA-Z0-9_]', '_', collection_name.lower())
        # Limit length and add UUID suffix for uniqueness
        sanitized_name = sanitized_name[:20]  # Limit to 20 chars
        table_id = f"{sanitized_name}_{str(uuid.uuid4()).replace('-', '_')[:8]}"

        # triggers PGVector to create both the vectorstore and DB entry
        get_vectorstore(table_id, collection_metadata=metadata)

        # Fetch the newly created table.
        async with get_db_connection() as conn:
            rec = await conn.fetchrow(
                """
                SELECT uuid, name, cmetadata
                  FROM langchain_pg_collection
                 WHERE name = $1
                   AND cmetadata->>'owner_id' = $2;
                """,
                table_id,
                self.user_id,
            )

        if not rec:
            return None

        collection_uuid = str(rec["uuid"])
        metadata = json.loads(rec["cmetadata"])
        name = metadata.pop("name")

        # Create owner permission entry for new permission system
        await self.permissions_manager.grant_permission(
            collection_uuid, self.user_id, PermissionLevel.OWNER
        )

        return {
            "uuid": collection_uuid,
            "name": name,
            "metadata": metadata,
            "permission_level": "owner",
        }

    async def update(
        self,
        collection_id: str,
        *,
        name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CollectionDetails:
        """Update collection metadata.

        Four cases:

        1) metadata only          → merge in metadata, keep old JSON->'name'
        2) metadata + new name    → merge metadata (including new 'name')
        3) new name only          → jsonb_set the 'name' key
        4) neither                → no-op, just fetch & return
        """
        # Check if user has edit permission
        permission_level = await self.permissions_manager.get_user_permission_level(
            collection_id
        )
        if permission_level not in ["owner", "editor"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to edit this collection",
            )

        # Case 4: no-op
        if metadata is None and name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must update at least 1 attribute.",
            )

        # Case 1 & 2: metadata supplied (with or without new name)
        if metadata is not None:
            # merge in owner_id + optional new name
            merged = metadata.copy()
            
            # Preserve original owner_id
            existing = await self.get(collection_id)
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Collection '{collection_id}' not found or you don't have access.",
                )
            merged["owner_id"] = existing["metadata"].get("owner_id", self.user_id)

            if name is not None:
                merged["name"] = name
            else:
                merged["name"] = existing["name"]

            metadata_json = json.dumps(merged)

            async with get_db_connection() as conn:
                rec = await conn.fetchrow(
                    """
                    UPDATE langchain_pg_collection
                       SET cmetadata = $1::jsonb
                     WHERE uuid = $2
                    RETURNING uuid, cmetadata;
                    """,
                    metadata_json,
                    collection_id,
                )

        # Case 3: name only
        else:  # metadata is None but name is not None
            async with get_db_connection() as conn:
                rec = await conn.fetchrow(
                    """
                    UPDATE langchain_pg_collection
                       SET cmetadata = jsonb_set(
                             cmetadata::jsonb,
                             '{name}',
                             to_jsonb($1::text),
                             true
                           )
                     WHERE uuid = $2
                    RETURNING uuid, cmetadata;
                    """,
                    name,
                    collection_id,
                )

        if not rec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection '{collection_id}' not found.",
            )

        full_meta = json.loads(rec["cmetadata"])
        friendly_name = full_meta.pop("name", "Unnamed")

        return {
            "uuid": str(rec["uuid"]),
            "name": friendly_name,
            "metadata": full_meta,
            "permission_level": permission_level,
        }

    async def delete(
        self,
        collection_id: str,
    ) -> int:
        """Delete a collection by UUID.
        Returns number of rows deleted (1).
        Raises PermissionError if user doesn't have owner permission.
        Raises ValueError if collection not found.
        """
        # Check if user has owner permission
        permission_level = await self.permissions_manager.get_user_permission_level(
            collection_id
        )
        if permission_level != "owner":
            raise PermissionError("Only owners can delete collections")

        async with get_db_connection() as conn:
            # Delete collection permissions first (due to foreign key)
            await conn.execute(
                """
                DELETE FROM collection_permissions
                WHERE collection_id = $1
                """,
                collection_id,
            )

            # Delete the collection
            result = await conn.execute(
                """
                DELETE FROM langchain_pg_collection
                WHERE uuid = $1
                """,
                collection_id,
            )
        
        rows_deleted = int(result.split()[-1])
        if rows_deleted == 0:
            raise ValueError(f"Collection with ID {collection_id} not found")
        
        return rows_deleted

    async def share_collection(
        self,
        collection_id: str,
        users_permissions: List[dict[str, Any]],
    ) -> dict[str, Any]:
        """Share a collection with multiple users."""
        shared_permissions = []
        errors = []

        for user_perm in users_permissions:
            try:
                # Ensure the permissions manager inherits service account flag
                if hasattr(self, '_is_service_account') and self._is_service_account:
                    self.permissions_manager._is_service_account = True
                
                await self.permissions_manager.grant_permission(
                    collection_id,
                    user_perm["user_id"],
                    PermissionLevel(user_perm["permission_level"]),
                )

                # Get the complete permission record with timestamps
                # Create a new permissions manager for querying to inherit service account flag
                query_permissions_manager = CollectionPermissionsManager(self.user_id)
                if hasattr(self, '_is_service_account') and self._is_service_account:
                    query_permissions_manager._is_service_account = True
                    
                all_permissions = await query_permissions_manager.list_collection_permissions(collection_id)
                # Find the permission record for this user
                user_permission = next(
                    (p for p in all_permissions if p["user_id"] == user_perm["user_id"]), 
                    None
                )
                
                if user_permission:
                    shared_permissions.append(user_permission)
                else:
                    # Fallback if we can't find the record (shouldn't happen)
                    shared_permissions.append({
                        "id": "",
                        "collection_id": collection_id,
                        "user_id": user_perm["user_id"],
                        "permission_level": user_perm["permission_level"],
                        "granted_by": self.user_id,
                        "created_at": None,
                        "updated_at": None,
                    })

            except Exception as e:
                errors.append(f"Failed to grant {user_perm['permission_level']} permission to {user_perm['user_id']}: {str(e)}")

        return {"shared_permissions": shared_permissions, "errors": errors}


class Collection:
    """A collection of documents.

    Use to add, delete, list, and search documents to a given collection.
    """

    def __init__(self, collection_id: str, user_id: str) -> None:
        """Initialize the collection by collection ID."""
        self.collection_id = collection_id
        self.user_id = user_id
        self.permissions_manager = CollectionPermissionsManager(user_id)
        self._is_service_account = False  # Track if this is being used by a service account

    async def _get_details_or_raise(self) -> dict[str, Any]:
        """Get collection details if user has access, otherwise raise an error."""
        collections_manager = CollectionsManager(self.user_id)
        if self._is_service_account:
            collections_manager._is_service_account = True
        details = await collections_manager.get(self.collection_id)
        if not details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        return details

    async def upsert(self, documents: list[Document]) -> list[str]:
        """Add one or more documents to the collection.
        
        If documents have document_id in metadata, they will be linked to document records.
        """
        # Check if user has edit permission
        permission_level = await self.permissions_manager.get_user_permission_level(
            self.collection_id
        )
        if permission_level not in ["owner", "editor"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to add documents to this collection",
            )

        details = await self._get_details_or_raise()
        store = get_vectorstore(collection_name=details["table_id"])
        
        # Process documents to handle document_id linking for new model
        processed_documents = []
        document_id_mapping = {}  # Map chunk index to document_id
        
        for i, doc in enumerate(documents):
            # Create a copy to avoid modifying the original
            processed_doc = Document(
                page_content=doc.page_content,
                metadata=doc.metadata.copy()
            )
            
            # Extract document_id from metadata if present
            if "document_id" in doc.metadata:
                document_id_mapping[i] = doc.metadata["document_id"]
            
            processed_documents.append(processed_doc)
        
        # Add documents to vector store (this creates the chunks)
        added_ids = store.add_documents(processed_documents)
        
        # Update metadata and document_id column for all created chunks
        if added_ids:
            async with get_db_connection() as conn:
                for i, chunk_id in enumerate(added_ids):
                    try:
                        # Get current metadata
                        current_metadata_row = await conn.fetchrow(
                            """
                            SELECT cmetadata FROM langconnect.langchain_pg_embedding 
                            WHERE id = $1 AND collection_id = $2
                            """,
                            chunk_id,
                            self.collection_id
                        )
                        
                        if current_metadata_row:
                            # Parse existing metadata
                            current_metadata = json.loads(current_metadata_row["cmetadata"]) if current_metadata_row["cmetadata"] else {}
                            
                            # Add chunk ID to metadata if not already present
                            if "id" not in current_metadata:
                                current_metadata["id"] = str(chunk_id)
                            
                            # Add collection_id to metadata if not already present  
                            if "collection_id" not in current_metadata:
                                current_metadata["collection_id"] = str(self.collection_id)
                            
                            # Add document_id to metadata if we have one
                            document_id = document_id_mapping.get(i)
                            if document_id:
                                current_metadata["document_id"] = document_id
                            
                            # Update both metadata and document_id column
                            await conn.execute(
                                """
                                UPDATE langconnect.langchain_pg_embedding 
                                SET cmetadata = $1, document_id = $2
                                WHERE id = $3 AND collection_id = $4
                                """,
                                json.dumps(current_metadata),
                                document_id,
                                chunk_id,
                                self.collection_id
                            )
                            
                            if document_id:
                                logger.info(f"Updated chunk {chunk_id}: added ID to metadata and linked to document {document_id}")
                            else:
                                logger.info(f"Updated chunk {chunk_id}: added ID to metadata")
                        
                    except Exception as e:
                        logger.error(f"Failed to update metadata for chunk {chunk_id}: {e}")
                        # Continue processing other chunks even if one fails
        
        return added_ids
    
    async def has_document_model(self) -> bool:
        """Check if this collection uses the new document model."""
        return await DocumentManager.collection_has_documents(self.collection_id)
    
    async def get_document_stats(self) -> dict[str, Any]:
        """Get document statistics for this collection."""
        return await DocumentManager.get_collection_document_stats(self.collection_id)
    
    def get_document_manager(self) -> DocumentManager:
        """Get a document manager instance for this collection."""
        return DocumentManager(self.collection_id, self.user_id)

    async def delete(
        self,
        *,
        file_id: Optional[str] = None,
    ) -> bool:
        """Delete embeddings by file id.

        A file id identifies the original file from which the chunks were generated.
        """
        # Check if user has edit permission
        permission_level = await self.permissions_manager.get_user_permission_level(
            self.collection_id
        )
        if permission_level not in ["owner", "editor"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete documents from this collection",
            )

        async with get_db_connection() as conn:
            delete_sql = """
                DELETE FROM langchain_pg_embedding AS lpe
                USING langchain_pg_collection AS lpc
                WHERE lpe.collection_id   = lpc.uuid
                  AND lpc.uuid             = $1
                  AND lpe.cmetadata->>'file_id'   = $2
            """
            # Params: collection UUID, file ID
            result = await conn.execute(
                delete_sql,
                self.collection_id,
                file_id,
            )
            # result is like "DELETE 3"
            deleted_count = int(result.split()[-1])
            logger.info(f"Deleted {deleted_count} embeddings for file {file_id!r}.")

            # For now if deleted count is 0, let's verify that the collection exists.
            if deleted_count == 0:
                await self._get_details_or_raise()
        return True

    async def list(self, *, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        """List one representative chunk per unique source (file, url, youtube, text) in this collection."""
        # Check if user has any access to this collection
        permission_level = await self.permissions_manager.get_user_permission_level(
            self.collection_id
        )
        if not permission_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this collection",
            )

        async with get_db_connection() as conn:
            rows = await conn.fetch(
                """
                WITH UniqueSourceChunks AS (
                  SELECT DISTINCT ON (
                    COALESCE(
                      lpe.cmetadata->>'file_id',
                      lpe.cmetadata->>'url',
                      lpe.cmetadata->>'youtube_video_id',
                      lpe.cmetadata->>'text_id',
                      lpe.cmetadata->>'title'
                    )
                  )
                    lpe.id,
                    COALESCE(
                      lpe.cmetadata->>'file_id',
                      lpe.cmetadata->>'url',
                      lpe.cmetadata->>'youtube_video_id',
                      lpe.cmetadata->>'text_id',
                      lpe.cmetadata->>'title'
                    ) AS source_key
                  FROM langchain_pg_embedding lpe
                  JOIN langchain_pg_collection lpc
                    ON lpe.collection_id = lpc.uuid
                  WHERE lpc.uuid = $1
                  ORDER BY source_key, lpe.id
                )
                SELECT emb.id,
                       emb.document,
                       emb.cmetadata
                FROM langchain_pg_embedding AS emb
                JOIN UniqueSourceChunks AS usc
                  ON emb.id = usc.id
                ORDER BY usc.source_key
                LIMIT  $2
                OFFSET $3
                """,
                self.collection_id,
                limit,
                offset,
            )

        docs: list[dict[str, Any]] = []
        for r in rows:
            metadata = json.loads(r["cmetadata"]) if r["cmetadata"] else {}
            docs.append(
                {
                    "id": str(r["id"]),
                    "content": r["document"],
                    "metadata": metadata,
                    "collection_id": str(self.collection_id),
                }
            )

        if not docs:
            # For now, if no documents, let's check that the collection exists.
            await self._get_details_or_raise()
        return docs

    async def get(self, document_id: str) -> dict[str, Any]:
        """Fetch a single chunk by its UUID, verifying collection access."""
        # Check if user has any access to this collection
        permission_level = await self.permissions_manager.get_user_permission_level(
            self.collection_id
        )
        if not permission_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this collection",
            )

        async with get_db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT e.id, e.document, e.cmetadata
                  FROM langchain_pg_embedding e
                  JOIN langchain_pg_collection c
                    ON e.collection_id = c.uuid
                 WHERE e.id = $1
                   AND c.uuid = $2
                """,
                document_id,
                self.collection_id,
            )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        metadata = json.loads(row["cmetadata"]) if row["cmetadata"] else {}
        return {
            "id": str(row["id"]),
            "content": row["document"],
            "metadata": metadata,
        }

    async def search(
        self, query: str, *, limit: int = 4, filter: Optional[dict[str, Any]] = None
    ) -> builtins.list[dict[str, Any]]:
        """Run a semantic similarity search in the vector store.
        Note: offset is applied client-side after retrieval.
        """
        # Check if user has any access to this collection
        permission_level = await self.permissions_manager.get_user_permission_level(
            self.collection_id
        )
        if not permission_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this collection",
            )

        details = await self._get_details_or_raise()
        store = get_vectorstore(collection_name=details["table_id"])
        results = store.similarity_search_with_score(query, k=limit, filter=filter)
        
        # Convert LangChain Document objects to our expected format
        formatted_results = []
        
        async with get_db_connection() as conn:
            for doc, score in results:
                # Get the chunk ID from metadata first, with fallback to database lookup
                doc_id = doc.metadata.get('id') or doc.metadata.get('uuid')
                document_id = doc.metadata.get('document_id')
                
                # If IDs are missing from metadata, try to find them in the database
                if not doc_id or not document_id:
                    try:
                        # Find the embedding by content and collection
                        db_row = await conn.fetchrow(
                            """
                            SELECT id, document_id, cmetadata 
                            FROM langconnect.langchain_pg_embedding 
                            WHERE collection_id = $1 AND document = $2
                            LIMIT 1
                            """,
                            self.collection_id,
                            doc.page_content[:500]  # Match on first 500 chars to handle long content
                        )
                        
                        if db_row:
                            # Use database values as fallback
                            if not doc_id:
                                doc_id = str(db_row["id"])
                            if not document_id and db_row["document_id"]:
                                document_id = str(db_row["document_id"])
                            
                            # Update metadata with missing IDs for consistency
                            if not doc.metadata.get('id'):
                                doc.metadata['id'] = doc_id
                            if not doc.metadata.get('document_id') and document_id:
                                doc.metadata['document_id'] = document_id
                                
                    except Exception as e:
                        logger.warning(f"Failed to lookup missing IDs for chunk: {e}")
                        # If lookup fails, use a fallback ID to avoid None
                        if not doc_id:
                            doc_id = f"unknown-{hash(doc.page_content[:100]) % 100000}"
                
                # Ensure we always have a valid doc_id
                if not doc_id:
                    doc_id = f"fallback-{hash(doc.page_content[:100]) % 100000}"
                
                formatted_results.append({
                    "id": doc_id,
                    "content": doc.page_content,  # LangChain uses page_content
                    "metadata": doc.metadata,
                    "similarity_score": float(score),  # Ensure score is a float
                })
        
        return formatted_results

    async def contextual_search(
        self,
        query: str,
        *,
        limit: int = 4,
        filter: Optional[dict[str, Any]] = None,
        return_surrounding_context: bool = False,
        max_context_characters: int = 2000,
        format_chunks_for_llm: bool = False,
    ) -> builtins.list[Any]:  # Changed to Any to handle both SearchResult and FormattedSearchResult
        """Run a contextual semantic similarity search with optional context expansion.
        
        Args:
            query: Search query text
            limit: Maximum number of results
            filter: Optional metadata filter
            return_surrounding_context: Whether to include surrounding context
            max_context_characters: Max characters for context expansion
            format_chunks_for_llm: Whether to format for LLM consumption
            
        Returns:
            List[SearchResult] when format_chunks_for_llm=False
            List[FormattedSearchResult] when format_chunks_for_llm=True
        """
        from langconnect.models.search import SearchResult, ContextExpansionConfig
        from langconnect.services.search_service import SearchService, SearchFormatter
        
        # Get base search results using existing method
        base_results = await self.search(query, limit=limit, filter=filter)
        
        # Convert to SearchResult objects with document metadata
        search_results = []
        async with get_db_connection() as conn:
            for result in base_results:
                # Get document metadata for this chunk
                document_metadata = {}
                document_id = result.get("metadata", {}).get("document_id", "")
                
                if document_id:
                    try:
                        doc_row = await conn.fetchrow(
                            """
                            SELECT cmetadata FROM langconnect.langchain_pg_document
                            WHERE id = $1 AND collection_id = $2
                            """,
                            document_id,
                            self.collection_id,
                        )
                        if doc_row and doc_row["cmetadata"]:
                            document_metadata = json.loads(doc_row["cmetadata"])
                    except Exception as e:
                        logger.warning(f"Failed to get document metadata for {document_id}: {e}")
                
                search_result = SearchResult(
                    id=result["id"],
                    page_content=result["content"],
                    metadata=result["metadata"],
                    score=result["similarity_score"],
                    document_id=document_id,
                    document_metadata=document_metadata,
                    supporting_context=[],  # Will be populated if context is requested
                )
                search_results.append(search_result)
        
        # Expand with context if requested
        if return_surrounding_context:
            search_service = SearchService(self.collection_id, self.user_id)
            config = ContextExpansionConfig(
                max_characters=max_context_characters,
                prefer_full_document=True,
                expansion_strategy="alternating",
            )
            search_results = await search_service.expand_search_results_with_context(
                search_results, config
            )
        
        # Format for LLM if requested
        if format_chunks_for_llm:
            from langconnect.models.search import LLMSearchResponse
            
            # Create combined formatted text
            formatted_text = SearchFormatter.create_combined_llm_text(search_results)
            
            # Return LLMSearchResponse with both formatted text and structured data
            return LLMSearchResponse(
                formatted_text=formatted_text,
                structured_results=search_results,
                total_found=len(search_results),
                query=query,
                contextual_options={
                    "return_surrounding_context": return_surrounding_context,
                    "max_context_characters": max_context_characters,
                    "format_chunks_for_llm": format_chunks_for_llm,
                }
            )
        
        return search_results

    async def keyword_search(
        self,
        keywords: List[str],
        *,
        limit: int = 4,
        filter: Optional[dict[str, Any]] = None,
        return_surrounding_context: bool = False,
        max_context_characters: int = 2000,
        format_chunks_for_llm: bool = False,
    ) -> builtins.list[Any]:
        """Run a keyword-based full-text search with optional context expansion.
        
        Args:
            keywords: List of keywords or phrases to search for
            limit: Maximum number of results
            filter: Optional metadata filter
            return_surrounding_context: Whether to include surrounding context
            max_context_characters: Max characters for context expansion
            format_chunks_for_llm: Whether to format for LLM consumption
            
        Returns:
            List[SearchResult] when format_chunks_for_llm=False
            LLMSearchResponse when format_chunks_for_llm=True
        """
        from langconnect.models.search import SearchResult, ContextExpansionConfig
        from langconnect.services.search_service import SearchService, SearchFormatter
        
        # Check if user has any access to this collection
        permission_level = await self.permissions_manager.get_user_permission_level(
            self.collection_id
        )
        if not permission_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this collection",
            )

        # Build PostgreSQL full-text search query
        # Convert keywords to tsquery format
        tsquery_parts = []
        for keyword in keywords:
            # Escape single quotes and handle phrases
            escaped_keyword = keyword.replace("'", "''")
            if " " in keyword:
                # For phrases, use exact phrase matching
                tsquery_parts.append(f"'{escaped_keyword}'")
            else:
                # For single words, use prefix matching
                tsquery_parts.append(f"'{escaped_keyword}':*")
        
        # Combine with OR logic
        tsquery_string = " | ".join(tsquery_parts)
        
        # Prepare metadata filter clause
        filter_clause = ""
        filter_params = []
        param_count = 3  # Starting after collection_id, tsquery_string, limit
        
        if filter:
            filter_conditions = []
            for key, value in filter.items():
                filter_conditions.append(f"e.cmetadata->>${param_count} = ${param_count + 1}")
                filter_params.extend([key, str(value)])
                param_count += 2
            
            if filter_conditions:
                filter_clause = " AND " + " AND ".join(filter_conditions)

        # Execute full-text search
        async with get_db_connection() as conn:
            query = f"""
                SELECT 
                    e.id,
                    e.document,
                    e.cmetadata,
                    e.document_id,
                    ts_rank_cd(to_tsvector('english', e.document), query) as rank_score
                FROM langconnect.langchain_pg_embedding e,
                     to_tsquery('english', $2) query
                WHERE e.collection_id = $1
                  AND to_tsvector('english', e.document) @@ query
                  {filter_clause}
                ORDER BY rank_score DESC
                LIMIT $3
            """
            
            params = [self.collection_id, tsquery_string, limit] + filter_params
            rows = await conn.fetch(query, *params)
        
        # Convert to SearchResult objects with document metadata
        search_results = []
        async with get_db_connection() as conn:
            for row in rows:
                # Parse metadata
                metadata = json.loads(row["cmetadata"]) if row["cmetadata"] else {}
                document_id = str(row["document_id"]) if row["document_id"] else ""
                
                # Get document metadata
                document_metadata = {}
                if document_id:
                    try:
                        doc_row = await conn.fetchrow(
                            """
                            SELECT cmetadata FROM langconnect.langchain_pg_document
                            WHERE id = $1 AND collection_id = $2
                            """,
                            document_id,
                            self.collection_id,
                        )
                        if doc_row and doc_row["cmetadata"]:
                            document_metadata = json.loads(doc_row["cmetadata"])
                    except Exception as e:
                        logger.warning(f"Failed to get document metadata for {document_id}: {e}")
                
                search_result = SearchResult(
                    id=str(row["id"]),
                    page_content=row["document"],
                    metadata=metadata,
                    score=float(row["rank_score"]),  # ts_rank_cd score
                    document_id=document_id,
                    document_metadata=document_metadata,
                    supporting_context=[],  # Will be populated if context is requested
                )
                search_results.append(search_result)
        
        # Expand with context if requested
        if return_surrounding_context:
            search_service = SearchService(self.collection_id, self.user_id)
            config = ContextExpansionConfig(
                max_characters=max_context_characters,
                prefer_full_document=True,
                expansion_strategy="alternating",
            )
            search_results = await search_service.expand_search_results_with_context(
                search_results, config
            )
        
        # Format for LLM if requested
        if format_chunks_for_llm:
            from langconnect.models.search import LLMSearchResponse
            
            # Create combined formatted text
            formatted_text = SearchFormatter.create_combined_llm_text(search_results)
            
            # Return LLMSearchResponse with both formatted text and structured data
            return LLMSearchResponse(
                formatted_text=formatted_text,
                structured_results=search_results,
                total_found=len(search_results),
                query=" | ".join(keywords),  # Show keywords as query
                contextual_options={
                    "return_surrounding_context": return_surrounding_context,
                    "max_context_characters": max_context_characters,
                    "format_chunks_for_llm": format_chunks_for_llm,
                }
            )
        
        return search_results

    async def hybrid_search(
        self,
        query: str,
        keywords: List[str],
        *,
        limit: int = 4,
        filter: Optional[dict[str, Any]] = None,
        return_surrounding_context: bool = False,
        max_context_characters: int = 2000,
        format_chunks_for_llm: bool = False,
        semantic_weight: float = 0.5,
    ) -> builtins.list[Any]:
        """Run a hybrid search combining semantic and keyword search with optional context expansion.
        
        Args:
            query: Semantic search query text
            keywords: List of keywords or phrases to search for
            limit: Maximum number of results
            filter: Optional metadata filter
            return_surrounding_context: Whether to include surrounding context
            max_context_characters: Max characters for context expansion
            format_chunks_for_llm: Whether to format for LLM consumption
            semantic_weight: Weight for semantic results (0.0-1.0)
            
        Returns:
            List[SearchResult] when format_chunks_for_llm=False
            LLMSearchResponse when format_chunks_for_llm=True
        """
        from langconnect.models.search import SearchResult, ContextExpansionConfig
        from langconnect.services.search_service import SearchService, SearchFormatter
        
        # Get results from both search methods
        # Use higher limit for each to ensure we have enough results to merge
        search_limit = min(limit * 2, 50)  # Cap at 50 to avoid performance issues
        
        # Run semantic search
        semantic_results = await self.search(query, limit=search_limit, filter=filter)
        
        # Run keyword search
        keyword_results_raw = await self.keyword_search(
            keywords, 
            limit=search_limit, 
            filter=filter,
            return_surrounding_context=False,  # We'll handle context later
            format_chunks_for_llm=False
        )
        
        # Normalize scores and combine results
        combined_results = {}  # Use dict to deduplicate by chunk ID
        
        # Process semantic results
        if semantic_results:
            # Normalize semantic scores to 0-1 range
            max_semantic_score = max(r["similarity_score"] for r in semantic_results)
            min_semantic_score = min(r["similarity_score"] for r in semantic_results)
            semantic_range = max_semantic_score - min_semantic_score if max_semantic_score != min_semantic_score else 1
            
            for result in semantic_results:
                normalized_score = (result["similarity_score"] - min_semantic_score) / semantic_range
                weighted_score = normalized_score * semantic_weight
                
                chunk_id = result["id"]
                if chunk_id not in combined_results:
                    combined_results[chunk_id] = {
                        "result": result,
                        "semantic_score": normalized_score,
                        "keyword_score": 0.0,
                        "combined_score": weighted_score,
                    }
                else:
                    # Update if semantic score is higher
                    combined_results[chunk_id]["semantic_score"] = max(
                        combined_results[chunk_id]["semantic_score"], 
                        normalized_score
                    )
                    combined_results[chunk_id]["combined_score"] = (
                        combined_results[chunk_id]["semantic_score"] * semantic_weight +
                        combined_results[chunk_id]["keyword_score"] * (1 - semantic_weight)
                    )
        
        # Process keyword results
        if keyword_results_raw:
            # Normalize keyword scores to 0-1 range
            max_keyword_score = max(r.score for r in keyword_results_raw)
            min_keyword_score = min(r.score for r in keyword_results_raw)
            keyword_range = max_keyword_score - min_keyword_score if max_keyword_score != min_keyword_score else 1
            
            for result in keyword_results_raw:
                normalized_score = (result.score - min_keyword_score) / keyword_range
                weighted_score = normalized_score * (1 - semantic_weight)
                
                chunk_id = result.id
                if chunk_id not in combined_results:
                    # Convert SearchResult back to dict format for consistency
                    result_dict = {
                        "id": result.id,
                        "content": result.page_content,
                        "metadata": result.metadata,
                        "similarity_score": result.score,  # Keep original score
                    }
                    combined_results[chunk_id] = {
                        "result": result_dict,
                        "semantic_score": 0.0,
                        "keyword_score": normalized_score,
                        "combined_score": weighted_score,
                    }
                else:
                    # Update keyword score and recalculate combined score
                    combined_results[chunk_id]["keyword_score"] = max(
                        combined_results[chunk_id]["keyword_score"], 
                        normalized_score
                    )
                    combined_results[chunk_id]["combined_score"] = (
                        combined_results[chunk_id]["semantic_score"] * semantic_weight +
                        combined_results[chunk_id]["keyword_score"] * (1 - semantic_weight)
                    )
        
        # Sort by combined score and take top results
        sorted_results = sorted(
            combined_results.values(), 
            key=lambda x: x["combined_score"], 
            reverse=True
        )[:limit]
        
        # Convert to SearchResult objects with document metadata
        search_results = []
        async with get_db_connection() as conn:
            for item in sorted_results:
                result = item["result"]
                
                # Get document metadata for this chunk
                document_metadata = {}
                document_id = result.get("metadata", {}).get("document_id", "")
                
                if document_id:
                    try:
                        doc_row = await conn.fetchrow(
                            """
                            SELECT cmetadata FROM langconnect.langchain_pg_document
                            WHERE id = $1 AND collection_id = $2
                            """,
                            document_id,
                            self.collection_id,
                        )
                        if doc_row and doc_row["cmetadata"]:
                            document_metadata = json.loads(doc_row["cmetadata"])
                    except Exception as e:
                        logger.warning(f"Failed to get document metadata for {document_id}: {e}")
                
                search_result = SearchResult(
                    id=result["id"],
                    page_content=result["content"],
                    metadata=result["metadata"],
                    score=item["combined_score"],  # Use combined score
                    document_id=document_id,
                    document_metadata=document_metadata,
                    supporting_context=[],  # Will be populated if context is requested
                )
                search_results.append(search_result)
        
        # Expand with context if requested
        if return_surrounding_context:
            search_service = SearchService(self.collection_id, self.user_id)
            config = ContextExpansionConfig(
                max_characters=max_context_characters,
                prefer_full_document=True,
                expansion_strategy="alternating",
            )
            search_results = await search_service.expand_search_results_with_context(
                search_results, config
            )
        
        # Format for LLM if requested
        if format_chunks_for_llm:
            from langconnect.models.search import LLMSearchResponse
            
            # Create combined formatted text
            formatted_text = SearchFormatter.create_combined_llm_text(search_results)
            
            # Return LLMSearchResponse with both formatted text and structured data
            return LLMSearchResponse(
                formatted_text=formatted_text,
                structured_results=search_results,
                total_found=len(search_results),
                query=f"Hybrid: '{query}' + keywords: {', '.join(keywords)}",
                contextual_options={
                    "return_surrounding_context": return_surrounding_context,
                    "max_context_characters": max_context_characters,
                    "format_chunks_for_llm": format_chunks_for_llm,
                    "semantic_weight": semantic_weight,
                }
            )
        
        return search_results
