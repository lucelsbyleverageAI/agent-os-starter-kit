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
    
    async def update_document_content(
        self,
        document_id: str,
        new_content: str
    ) -> bool:
        """Update document content and mark for reprocessing.
        
        Args:
            document_id: Document UUID to update
            new_content: New content to set
            
        Returns:
            True if update successful, False otherwise
        """
        async with get_db_connection() as conn:
            query = """
                UPDATE langconnect.langchain_pg_document
                SET 
                    content = $1,
                    updated_at = NOW(),
                    cmetadata = jsonb_set(
                        cmetadata,
                        '{processing_status}',
                        '"pending"'
                    )
                WHERE id = $2 AND collection_id = $3
                RETURNING id
            """
            result = await conn.fetchrow(query, new_content, document_id, self.collection_id)
            return result is not None
    
    async def update_document_metadata(
        self,
        document_id: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """Update document metadata.
        
        Args:
            document_id: Document UUID to update
            metadata: New metadata dictionary
            
        Returns:
            True if update successful, False otherwise
        """
        async with get_db_connection() as conn:
            query = """
                UPDATE langconnect.langchain_pg_document
                SET 
                    cmetadata = $1,
                    updated_at = NOW()
                WHERE id = $2 AND collection_id = $3
                RETURNING id
            """
            result = await conn.fetchrow(query, json.dumps(metadata), document_id, self.collection_id)
            return result is not None
    
    async def get_document_with_lines(
        self,
        document_id: str,
        offset: int = 0,
        limit: int = 2000,
        include_line_numbers: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get document content with line number formatting.
        
        Args:
            document_id: Document UUID to read
            offset: Starting line number (0-indexed)
            limit: Number of lines to return
            include_line_numbers: Whether to include line numbers in output
            
        Returns:
            Dictionary with formatted content and metadata, or None if not found
        """
        async with get_db_connection() as conn:
            if include_line_numbers:
                # Line-numbered format
                query = """
                    WITH lines AS (
                      SELECT 
                        row_number() OVER () as line_num,
                        line_text
                      FROM (
                        SELECT unnest(string_to_array(content, E'\n')) as line_text
                        FROM langconnect.langchain_pg_document
                        WHERE id = $1 AND collection_id = $2
                      ) subq
                    )
                    SELECT 
                      string_agg(
                        lpad(line_num::text, 6, ' ') || '|' || line_text,
                        E'\n'
                        ORDER BY line_num
                      ) as content,
                      max(line_num) as total_lines,
                      min(line_num) as start_line,
                      max(line_num) as end_line
                    FROM lines
                    WHERE line_num > $3 AND line_num <= $3 + $4;
                """
            else:
                # Plain format
                query = """
                    WITH lines AS (
                      SELECT 
                        row_number() OVER () as line_num,
                        line_text
                      FROM (
                        SELECT unnest(string_to_array(content, E'\n')) as line_text
                        FROM langconnect.langchain_pg_document
                        WHERE id = $1 AND collection_id = $2
                      ) subq
                    )
                    SELECT 
                      string_agg(line_text, E'\n' ORDER BY line_num) as content,
                      max(line_num) as total_lines,
                      min(line_num) as start_line,
                      max(line_num) as end_line
                    FROM lines
                    WHERE line_num > $3 AND line_num <= $3 + $4;
                """
            
            result = await conn.fetchrow(query, document_id, self.collection_id, offset, limit)
            
            if not result:
                return None
            
            # Get document metadata
            doc = await self.get_document(document_id)
            
            if not doc:
                return None
            
            # Calculate total bytes and actual total lines from original content
            size_query = """
                SELECT 
                    LENGTH(content) as total_bytes,
                    (LENGTH(content) - LENGTH(REPLACE(content, E'\n', ''))) + 1 as actual_total_lines
                FROM langconnect.langchain_pg_document
                WHERE id = $1 AND collection_id = $2
            """
            size_result = await conn.fetchrow(size_query, document_id, self.collection_id)
            
            actual_total_lines = size_result["actual_total_lines"] if size_result else 0
            
            return {
                "content": result["content"] or "",
                "total_lines": actual_total_lines,
                "total_bytes": size_result["total_bytes"] if size_result else 0,
                "line_range": {
                    "start": result["start_line"] or 0,
                    "end": result["end_line"] or 0
                },
                "document_name": doc.get("metadata", {}).get("title") or doc.get("metadata", {}).get("original_filename") or "Untitled",
                "collection_id": self.collection_id,
                "document_id": document_id,
                "truncated": (result["end_line"] or 0) < actual_total_lines
            }
    
    async def search_documents_by_pattern(
        self,
        pattern: str,
        case_sensitive: bool = False,
        max_results: int = 100,
        context_lines: int = 2,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search for pattern across documents using regex (grep-like functionality).
        
        Args:
            pattern: Regex pattern to search for
            case_sensitive: Whether search should be case sensitive
            max_results: Maximum number of matches to return
            context_lines: Number of lines to include before/after matches
            document_ids: Optional list of specific document IDs to search
            
        Returns:
            List of match dictionaries with line number, content, and context
        """
        async with get_db_connection() as conn:
            # Build the query with optional document filter
            doc_filter = ""
            params = [self.collection_id, pattern, max_results]
            if document_ids:
                doc_filter = "AND d.id = ANY($4::uuid[])"
                params.append(document_ids)
            
            # Use regex operator based on case sensitivity
            regex_op = "~" if case_sensitive else "~*"
            
            query = f"""
                WITH line_matches AS (
                  SELECT 
                    d.id as document_id,
                    d.cmetadata,
                    t.line_num,
                    t.line_text
                  FROM langconnect.langchain_pg_document d,
                       LATERAL (
                         SELECT 
                           row_number() OVER () as line_num,
                           line_text
                         FROM unnest(string_to_array(d.content, E'\n')) as line_text
                       ) t
                  WHERE d.collection_id = $1
                    {doc_filter}
                    AND t.line_text {regex_op} $2
                  LIMIT $3
                )
                SELECT 
                  lm.document_id,
                  lm.cmetadata,
                  lm.line_num,
                  lm.line_text
                FROM line_matches lm
                ORDER BY lm.document_id, lm.line_num;
            """
            
            rows = await conn.fetch(query, *params)
            
            matches = []
            for row in rows:
                metadata = json.loads(row["cmetadata"]) if row["cmetadata"] else {}
                document_name = (
                    metadata.get("title") or 
                    metadata.get("original_filename") or 
                    metadata.get("source_name") or 
                    "Untitled"
                )
                
                match = {
                    "document_id": str(row["document_id"]),
                    "collection_id": self.collection_id,
                    "document_name": document_name,
                    "line_number": row["line_num"],
                    "line_content": row["line_text"],
                }
                
                # Get context lines if requested
                if context_lines > 0:
                    context = await self._get_line_context(
                        str(row["document_id"]),
                        row["line_num"],
                        context_lines
                    )
                    match["context_before"] = context["before"]
                    match["context_after"] = context["after"]
                
                matches.append(match)
            
            return matches
    
    async def _get_line_context(
        self,
        document_id: str,
        line_number: int,
        context_lines: int
    ) -> Dict[str, List[str]]:
        """Get lines before and after a specific line number.
        
        Args:
            document_id: Document UUID
            line_number: Target line number
            context_lines: Number of lines to get before and after
            
        Returns:
            Dictionary with 'before' and 'after' lists of line strings
        """
        async with get_db_connection() as conn:
            query = """
                WITH lines AS (
                  SELECT 
                    row_number() OVER () as line_num,
                    line_text
                  FROM unnest(string_to_array(
                    (SELECT content FROM langconnect.langchain_pg_document 
                     WHERE id = $1 AND collection_id = $2),
                    E'\n'
                  )) as line_text
                )
                SELECT line_text, line_num
                FROM lines
                WHERE line_num BETWEEN $3 - $4 AND $3 + $4
                  AND line_num != $3
                ORDER BY line_num;
            """
            
            rows = await conn.fetch(
                query,
                document_id,
                self.collection_id,
                line_number,
                context_lines
            )
            
            before = []
            after = []
            
            for row in rows:
                if row["line_num"] < line_number:
                    before.append(row["line_text"])
                else:
                    after.append(row["line_text"])
            
            return {
                "before": before,
                "after": after
            }
    
    async def delete_document_embeddings(self, document_id: str) -> int:
        """Delete all embeddings associated with a document.
        
        Args:
            document_id: Document UUID
            
        Returns:
            Number of embeddings deleted
        """
        async with get_db_connection() as conn:
            query = """
                DELETE FROM langconnect.langchain_pg_embedding
                WHERE document_id = $1 AND collection_id = $2
            """
            result = await conn.execute(query, document_id, self.collection_id)
            # Extract count from result string like "DELETE 15"
            return int(result.split()[-1]) if result and " " in result else 0 