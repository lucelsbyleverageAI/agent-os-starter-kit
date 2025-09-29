"""Document management service for langchain_pg_document table."""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID, uuid4

from langconnect.database.connection import get_db_connection

logger = logging.getLogger(__name__)


class DocumentManager:
    """Manager for document-level operations with the langchain_pg_document table."""
    
    def __init__(self, collection_id: str, user_id: str):
        """Initialize document manager for a specific collection.
        
        Args:
            collection_id: Collection UUID
            user_id: User ID for permission checks
        """
        self.collection_id = collection_id
        self.user_id = user_id
    
    async def create_document(
        self, 
        content: str, 
        metadata: Dict[str, Any],
        document_id: Optional[str] = None
    ) -> str:
        """Create a new document in the collection.
        
        Args:
            content: Full document content
            metadata: Document-level metadata
            document_id: Optional specific document ID (generates UUID if not provided)
            
        Returns:
            Document ID
        """
        doc_id = document_id or str(uuid4())
        
        async with get_db_connection() as conn:
            query = """
                INSERT INTO langconnect.langchain_pg_document 
                (id, collection_id, content, cmetadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, NOW(), NOW())
                RETURNING id
            """
            
            result = await conn.fetchrow(
                query,
                doc_id,
                self.collection_id,
                content,
                json.dumps(metadata)
            )
            
            if not result:
                raise RuntimeError(f"Failed to create document {doc_id}")
            
            logger.info(f"Created document {doc_id} in collection {self.collection_id}")
            return str(result["id"])
    
    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID.
        
        Args:
            document_id: Document UUID
            
        Returns:
            Document data or None if not found
        """
        async with get_db_connection() as conn:
            query = """
                SELECT id, collection_id, content, cmetadata, created_at, updated_at
                FROM langconnect.langchain_pg_document
                WHERE id = $1 AND collection_id = $2
            """
            
            result = await conn.fetchrow(query, document_id, self.collection_id)
            
            if not result:
                return None
            
            return {
                "id": str(result["id"]),
                "collection_id": str(result["collection_id"]),
                "content": result["content"],
                "metadata": json.loads(result["cmetadata"]) if result["cmetadata"] else {},
                "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
            }
    
    async def list_documents(
        self, 
        limit: int = 10, 
        offset: int = 0,
        include_content: bool = False
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List documents in the collection with optimized chunk counts.
        
        Args:
            limit: Maximum number of documents to return
            offset: Number of documents to skip
            include_content: Whether to include full document content
            
        Returns:
            Tuple of (documents list, total count)
        """
        async with get_db_connection() as conn:
            # Select fields based on whether content is requested
            content_field = "d.content" if include_content else "NULL as content"
            
            # Optimized query that gets chunk counts in a single query using LEFT JOIN
            query = f"""
                SELECT 
                    d.id, 
                    d.collection_id, 
                    {content_field}, 
                    d.cmetadata, 
                    d.created_at, 
                    d.updated_at,
                    COALESCE(chunk_counts.chunk_count, 0) as chunk_count
                FROM langconnect.langchain_pg_document d
                LEFT JOIN (
                    SELECT 
                        document_id, 
                        COUNT(*) as chunk_count 
                    FROM langconnect.langchain_pg_embedding 
                    WHERE document_id IS NOT NULL
                    GROUP BY document_id
                ) chunk_counts ON d.id = chunk_counts.document_id
                WHERE d.collection_id = $1
                ORDER BY d.created_at DESC
                LIMIT $2 OFFSET $3
            """
            
            results = await conn.fetch(query, self.collection_id, limit, offset)
            
            # Get total count (unchanged)
            count_query = """
                SELECT COUNT(*) 
                FROM langconnect.langchain_pg_document
                WHERE collection_id = $1
            """
            total_count = await conn.fetchval(count_query, self.collection_id)
            
            documents = []
            for result in results:
                doc = {
                    "id": str(result["id"]),
                    "collection_id": str(result["collection_id"]),
                    "metadata": json.loads(result["cmetadata"]) if result["cmetadata"] else {},
                    "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                    "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
                    "chunk_count": result["chunk_count"],  # Now included in the main query
                }
                
                if include_content and result["content"]:
                    doc["content"] = result["content"]
                
                documents.append(doc)
            
            return documents, total_count
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its associated chunks.
        
        Args:
            document_id: Document UUID
            
        Returns:
            True if document was deleted
        """
        async with get_db_connection() as conn:
            # Delete document (chunks will have document_id set to NULL due to FK constraint)
            query = """
                DELETE FROM langconnect.langchain_pg_document
                WHERE id = $1 AND collection_id = $2
                RETURNING id
            """
            
            result = await conn.fetchrow(query, document_id, self.collection_id)
            
            if result:
                logger.info(f"Deleted document {document_id} from collection {self.collection_id}")
                return True
            else:
                logger.warning(f"Document {document_id} not found or access denied")
                return False
    
    async def update_document_metadata(
        self, 
        document_id: str, 
        metadata: Dict[str, Any]
    ) -> bool:
        """Update document metadata.
        
        Args:
            document_id: Document UUID
            metadata: New metadata to merge/replace
            
        Returns:
            True if document was updated
        """
        async with get_db_connection() as conn:
            query = """
                UPDATE langconnect.langchain_pg_document
                SET cmetadata = $1, updated_at = NOW()
                WHERE id = $2 AND collection_id = $3
                RETURNING id
            """
            
            result = await conn.fetchrow(
                query,
                json.dumps(metadata),
                document_id,
                self.collection_id
            )
            
            if result:
                logger.info(f"Updated metadata for document {document_id}")
                return True
            else:
                logger.warning(f"Document {document_id} not found for metadata update")
                return False
    
    async def get_document_chunks(self, document_id: str) -> List[Dict[str, Any]]:
        """Get all chunks belonging to a document.
        
        Args:
            document_id: Document UUID
            
        Returns:
            List of chunk data
        """
        async with get_db_connection() as conn:
            query = """
                SELECT id, document, cmetadata
                FROM langconnect.langchain_pg_embedding
                WHERE document_id = $1
                ORDER BY (cmetadata->>'chunk_index')::int
            """
            
            results = await conn.fetch(query, document_id)
            
            chunks = []
            for result in results:
                chunk = {
                    "id": str(result["id"]),
                    "content": result["document"],
                    "metadata": json.loads(result["cmetadata"]) if result["cmetadata"] else {},
                }
                chunks.append(chunk)
            
            return chunks
    
    async def search_documents(
        self, 
        query: str, 
        limit: int = 10,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search documents by content and metadata.
        
        Args:
            query: Search query
            limit: Maximum results
            metadata_filter: Optional metadata filters
            
        Returns:
            List of matching documents
        """
        async with get_db_connection() as conn:
            # Build search query
            where_conditions = ["collection_id = $1"]
            params = [self.collection_id]
            param_count = 2
            
            # Add text search
            if query.strip():
                where_conditions.append(f"document ILIKE ${param_count}")
                params.append(f"%{query}%")
                param_count += 1
            
            # Add metadata filter
            if metadata_filter:
                for key, value in metadata_filter.items():
                    where_conditions.append(f"cmetadata->>${param_count} = ${param_count + 1}")
                    params.extend([key, str(value)])
                    param_count += 2
            
            where_clause = " AND ".join(where_conditions)
            
            search_query = f"""
                SELECT id, collection_id, content, cmetadata, created_at, updated_at
                FROM langconnect.langchain_pg_document
                WHERE {where_clause}
                ORDER BY updated_at DESC
                LIMIT ${param_count}
            """
            params.append(limit)
            
            results = await conn.fetch(search_query, *params)
            
            documents = []
            for result in results:
                doc = {
                    "id": str(result["id"]),
                    "collection_id": str(result["collection_id"]),
                    "content": result["content"],
                    "metadata": json.loads(result["cmetadata"]) if result["cmetadata"] else {},
                    "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                    "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
                }
                documents.append(doc)
            
            return documents
    
    @staticmethod
    async def collection_has_documents(collection_id: str) -> bool:
        """Check if a collection uses the new document model.
        
        Args:
            collection_id: Collection UUID
            
        Returns:
            True if collection has documents in the document table
        """
        async with get_db_connection() as conn:
            query = """
                SELECT EXISTS(
                    SELECT 1 FROM langconnect.langchain_pg_document
                    WHERE collection_id = $1
                    LIMIT 1
                )
            """
            
            result = await conn.fetchval(query, collection_id)
            return bool(result)
    
    @staticmethod
    async def get_collection_document_stats(collection_id: str) -> Dict[str, Any]:
        """Get statistics about documents in a collection.
        
        Args:
            collection_id: Collection UUID
            
        Returns:
            Statistics dictionary
        """
        async with get_db_connection() as conn:
            query = """
                SELECT 
                    COUNT(*) as document_count,
                    AVG(LENGTH(content)) as avg_content_length,
                    MAX(LENGTH(content)) as max_content_length,
                    MIN(LENGTH(content)) as min_content_length,
                    COUNT(CASE WHEN cmetadata->>'source_type' = 'file' THEN 1 END) as file_documents,
                    COUNT(CASE WHEN cmetadata->>'source_type' = 'url' THEN 1 END) as url_documents,
                    COUNT(CASE WHEN cmetadata->>'source_type' = 'youtube' THEN 1 END) as youtube_documents,
                    COUNT(CASE WHEN cmetadata->>'source_type' = 'text' THEN 1 END) as text_documents
                FROM langconnect.langchain_pg_document
                WHERE collection_id = $1
            """
            
            result = await conn.fetchrow(query, collection_id)
            
            if not result or result["document_count"] == 0:
                return {
                    "document_count": 0,
                    "has_documents": False,
                }
            
            return {
                "document_count": result["document_count"],
                "has_documents": True,
                "avg_content_length": int(result["avg_content_length"] or 0),
                "max_content_length": result["max_content_length"] or 0,
                "min_content_length": result["min_content_length"] or 0,
                "source_breakdown": {
                    "file": result["file_documents"] or 0,
                    "url": result["url_documents"] or 0,
                    "youtube": result["youtube_documents"] or 0,
                    "text": result["text_documents"] or 0,
                }
            }
    
    async def check_duplicate_by_content_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """Check if a document with the same content hash exists in the collection.
        
        Args:
            content_hash: SHA-256 hash of the document content
            
        Returns:
            Document data if duplicate found, None otherwise
        """
        async with get_db_connection() as conn:
            query = """
                SELECT id, collection_id, cmetadata, created_at, updated_at
                FROM langconnect.langchain_pg_document
                WHERE collection_id = $1 AND cmetadata->>'content_hash' = $2
                LIMIT 1
            """
            
            result = await conn.fetchrow(query, self.collection_id, content_hash)
            
            if not result:
                return None
            
            metadata = json.loads(result["cmetadata"]) if result["cmetadata"] else {}
            
            return {
                "id": str(result["id"]),
                "collection_id": str(result["collection_id"]),
                "metadata": metadata,
                "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
                "title": metadata.get("title", "Untitled"),
                "original_filename": metadata.get("original_filename", "unknown"),
            }
    
    async def check_duplicate_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """Check if a document with the same filename exists in the collection.
        
        Args:
            filename: Original filename to check
            
        Returns:
            Document data if duplicate found, None otherwise
        """
        async with get_db_connection() as conn:
            query = """
                SELECT id, collection_id, cmetadata, created_at, updated_at
                FROM langconnect.langchain_pg_document
                WHERE collection_id = $1 AND cmetadata->>'original_filename' = $2
                LIMIT 1
            """
            
            result = await conn.fetchrow(query, self.collection_id, filename)
            
            if not result:
                return None
            
            metadata = json.loads(result["cmetadata"]) if result["cmetadata"] else {}
            
            return {
                "id": str(result["id"]),
                "collection_id": str(result["collection_id"]),
                "metadata": metadata,
                "created_at": result["created_at"].isoformat() if result["created_at"] else None,
                "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
                "title": metadata.get("title", "Untitled"),
                "original_filename": metadata.get("original_filename", "unknown"),
                "content_hash": metadata.get("content_hash"),
            } 