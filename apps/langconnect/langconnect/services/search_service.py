"""Search service for handling contextual search operations."""

import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from langconnect.database.connection import get_db_connection
from langconnect.models.search import (
    SearchResult,
    ChunkObject,
    DocumentObject,
    SupportingContext,
    ContextExpansionConfig,
    ContextExpansionResult,
    FormattedSearchResult,
)

logger = logging.getLogger(__name__)


class SearchService:
    """Service for handling search operations with contextual expansion."""

    def __init__(self, collection_id: str, user_id: str):
        """Initialize search service for a specific collection."""
        self.collection_id = collection_id
        self.user_id = user_id

    async def expand_search_results_with_context(
        self,
        base_results: List[SearchResult],
        config: ContextExpansionConfig,
    ) -> List[SearchResult]:
        """Expand search results with surrounding context.
        
        Args:
            base_results: Original search results from vector search
            config: Configuration for context expansion
            
        Returns:
            Enhanced search results with supporting context
        """
        enhanced_results = []

        for result in base_results:
            try:
                # Get document metadata if not already present
                if not result.document_id or not result.document_metadata:
                    document_info = await self._get_document_info_for_chunk(result.id)
                    if document_info:
                        result.document_id = document_info["document_id"]
                        result.document_metadata = document_info["document_metadata"]

                # Expand context for this result
                expansion_result = await self._expand_single_result_context(result, config)
                
                # Update the result with expanded context
                result.supporting_context = expansion_result.expanded_context
                enhanced_results.append(result)

            except Exception as e:
                logger.error(f"Failed to expand context for result {result.id}: {e}")
                # Add result without context on error
                enhanced_results.append(result)

        return enhanced_results

    async def _expand_single_result_context(
        self,
        result: SearchResult,
        config: ContextExpansionConfig,
    ) -> ContextExpansionResult:
        """Expand context for a single search result.
        
        Args:
            result: Original search result
            config: Expansion configuration
            
        Returns:
            Context expansion result
        """
        # First, try to get the full document
        if config.prefer_full_document:
            document_content = await self._get_full_document_content(result.document_id)
            if document_content and len(document_content["content"]) <= config.max_characters:
                # Return full document as context
                document_obj = DocumentObject(
                    document_id=result.document_id,
                    document_content=document_content["content"],
                    document_metadata=document_content["metadata"],
                    document_created_at=document_content.get("created_at"),
                    document_updated_at=document_content.get("updated_at"),
                )
                
                return ContextExpansionResult(
                    original_chunk=result,
                    expanded_context=[document_obj],
                    context_type="full_document",
                    total_characters=len(document_content["content"]),
                    truncated=False,
                )

        # If full document is too large, expand with surrounding chunks
        surrounding_chunks = await self._get_surrounding_chunks(
            result.document_id,
            result.id,
            config.max_characters,
        )
        
        context_objects = []
        total_chars = 0
        
        for chunk_data in surrounding_chunks:
            chunk_obj = ChunkObject(
                chunk_id=chunk_data["chunk_id"],
                chunk_content=chunk_data["chunk_content"],
                chunk_metadata=chunk_data["chunk_metadata"],
                chunk_created_at=chunk_data.get("chunk_created_at"),
                chunk_updated_at=chunk_data.get("chunk_updated_at"),
                document_id=result.document_id,
                document_metadata=result.document_metadata,
            )
            context_objects.append(chunk_obj)
            total_chars += len(chunk_data["chunk_content"])

        return ContextExpansionResult(
            original_chunk=result,
            expanded_context=context_objects,
            context_type="expanded_chunks" if context_objects else "none",
            total_characters=total_chars,
            truncated=total_chars >= config.max_characters,
        )

    async def _get_document_info_for_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Get document information for a given chunk."""
        async with get_db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT d.id as document_id, d.cmetadata as document_metadata
                FROM langconnect.langchain_pg_document d
                JOIN langconnect.langchain_pg_embedding e ON d.id = e.document_id
                WHERE e.id = $1 AND e.collection_id = $2
                """,
                chunk_id,
                self.collection_id,
            )
            
            if not row:
                return None
                
            return {
                "document_id": str(row["document_id"]),
                "document_metadata": json.loads(row["document_metadata"]) if row["document_metadata"] else {},
            }

    async def _get_full_document_content(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get full document content and metadata."""
        async with get_db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT content, cmetadata, created_at, updated_at
                FROM langconnect.langchain_pg_document
                WHERE id = $1 AND collection_id = $2
                """,
                document_id,
                self.collection_id,
            )
            
            if not row:
                return None
                
            return {
                "content": row["content"],
                "metadata": json.loads(row["cmetadata"]) if row["cmetadata"] else {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    async def _get_surrounding_chunks(
        self,
        document_id: str,
        found_chunk_id: str,
        max_characters: int,
    ) -> List[Dict[str, Any]]:
        """Get surrounding chunks using alternating expansion strategy.
        
        Args:
            document_id: Parent document ID
            found_chunk_id: The original found chunk ID
            max_characters: Maximum total characters to return
            
        Returns:
            List of chunk data dictionaries ordered by chunk_index
        """
        async with get_db_connection() as conn:
            # Get all chunks for this document, ordered by chunk_index
            rows = await conn.fetch(
                """
                SELECT id, document, cmetadata, created_at, updated_at
                FROM langconnect.langchain_pg_embedding
                WHERE document_id = $1 AND collection_id = $2
                ORDER BY COALESCE((cmetadata->>'chunk_index')::int, 999999)
                """,
                document_id,
                self.collection_id,
            )
            
            if not rows:
                return []

            # Find the index of the original found chunk
            chunk_lookup = {str(row["id"]): i for i, row in enumerate(rows)}
            found_chunk_index = chunk_lookup.get(found_chunk_id)
            
            if found_chunk_index is None:
                logger.warning(f"Could not find chunk {found_chunk_id} in document {document_id}")
                return []

            # Implement alternating expansion strategy
            selected_chunks = []
            total_chars = 0
            
            # Start with chunks around the found chunk (excluding the found chunk itself)
            distance = 1
            max_distance = len(rows)
            
            while distance < max_distance and total_chars < max_characters:
                added_any = False
                
                # Try chunk before
                before_index = found_chunk_index - distance
                if before_index >= 0:
                    chunk_data = self._parse_chunk_row(rows[before_index])
                    if total_chars + len(chunk_data["chunk_content"]) <= max_characters:
                        selected_chunks.insert(0, chunk_data)  # Insert at beginning to maintain order
                        total_chars += len(chunk_data["chunk_content"])
                        added_any = True
                
                # Try chunk after
                after_index = found_chunk_index + distance
                if after_index < len(rows):
                    chunk_data = self._parse_chunk_row(rows[after_index])
                    if total_chars + len(chunk_data["chunk_content"]) <= max_characters:
                        selected_chunks.append(chunk_data)
                        total_chars += len(chunk_data["chunk_content"])
                        added_any = True
                
                if not added_any:
                    break
                    
                distance += 1

            return selected_chunks

    def _parse_chunk_row(self, row) -> Dict[str, Any]:
        """Parse a database row into chunk data dictionary."""
        metadata = json.loads(row["cmetadata"]) if row["cmetadata"] else {}
        
        return {
            "chunk_id": str(row["id"]),
            "chunk_content": row["document"],
            "chunk_metadata": metadata,
            "chunk_created_at": row["created_at"],
            "chunk_updated_at": row["updated_at"],
        }


class SearchFormatter:
    """Reusable formatter for search results."""

    @staticmethod
    def format_results_for_llm(results: List[SearchResult]) -> List[FormattedSearchResult]:
        """Format search results for LLM consumption.
        
        Args:
            results: Search results with supporting context
            
        Returns:
            List of formatted results as markdown
        """
        # Group results by document
        document_groups = SearchFormatter._group_results_by_document(results)
        
        formatted_results = []
        
        for doc_id, doc_results in document_groups.items():
            # Get document metadata from first result
            doc_metadata = doc_results[0].document_metadata
            doc_title = doc_metadata.get("title", "Untitled Document")
            doc_source = doc_metadata.get("source", doc_metadata.get("original_filename", "Unknown source"))
            
            markdown_content = SearchFormatter._format_document_group(
                doc_title, doc_source, doc_metadata, doc_results
            )
            
            formatted_result = FormattedSearchResult(
                formatted_content=markdown_content,
                source_results=doc_results,
            )
            formatted_results.append(formatted_result)
        
        return formatted_results

    @staticmethod
    def create_combined_llm_text(results: List[SearchResult]) -> str:
        """Create a single combined formatted text from all search results.
        
        Args:
            results: Search results with supporting context
            
        Returns:
            Single markdown string combining all results with improved formatting
        """
        if not results:
            return "No search results found."
        
        # Group results by document
        document_groups = SearchFormatter._group_results_by_document(results)
        
        # Combine all formatted content into a single text
        combined_parts = []
        
        # Add header
        combined_parts.append("# Search Results\n\n")
        
        for i, (doc_id, doc_results) in enumerate(document_groups.items(), 1):
            # Get document metadata from first result
            doc_metadata = doc_results[0].document_metadata
            doc_title = doc_metadata.get("title", "Untitled Document")
            doc_source = doc_metadata.get("source_name") or doc_metadata.get("original_filename", "Unknown source")
            
            # Document header with proper spacing
            combined_parts.append(f"## Document {i}: {doc_title}\n")
            combined_parts.append(f"**Source:** {doc_source}\n\n")
            
            # Check if any result has full document in supporting context
            full_doc_result = None
            for result in doc_results:
                for context in result.supporting_context:
                    if context.type == "document":
                        full_doc_result = context
                        break
                if full_doc_result:
                    break
            
            if full_doc_result:
                # Display full document with better formatting
                combined_parts.append("### Full Document Content\n\n")
                content = full_doc_result.document_content.strip()
                # Ensure proper line breaks and spacing
                content = content.replace('\n\n\n', '\n\n')  # Remove excessive line breaks
                combined_parts.append(f"{content}\n\n")
            else:
                # Display chunks with improved formatting
                combined_parts.append("### Relevant Content Sections\n\n")
                
                # Collect all unique chunks (from main results + supporting context)
                all_chunks = []
                chunk_ids_seen = set()
                
                for result in doc_results:
                    # Add main result chunk
                    if result.id not in chunk_ids_seen:
                        all_chunks.append({
                            "id": result.id,
                            "content": result.page_content,
                            "metadata": result.metadata,
                            "is_matched": True,
                            "score": result.score,
                        })
                        chunk_ids_seen.add(result.id)
                    
                    # Add supporting chunks
                    for context in result.supporting_context:
                        if context.type == "chunk" and context.chunk_id not in chunk_ids_seen:
                            all_chunks.append({
                                "id": context.chunk_id,
                                "content": context.chunk_content,
                                "metadata": context.chunk_metadata,
                                "is_matched": False,
                                "score": None,
                            })
                            chunk_ids_seen.add(context.chunk_id)
                
                # Sort chunks by chunk_index if available
                all_chunks.sort(key=lambda x: x["metadata"].get("chunk_index", 999999))
                
                # Format each chunk with improved structure
                for j, chunk in enumerate(all_chunks):
                    chunk_index = chunk["metadata"].get("chunk_index")
                    
                    # Create section header
                    if chunk["is_matched"]:
                        section_title = f"**Section {j+1} [SEARCH MATCH"
                        if chunk["score"] is not None:
                            section_title += f" - Score: {chunk['score']:.3f}"
                        section_title += "]**"
                    else:
                        section_title = f"**Section {j+1} [CONTEXT]**"
                    
                    if chunk_index is not None:
                        section_title += f" (Chunk {chunk_index})"
                    
                    combined_parts.append(f"{section_title}\n\n")
                    
                    # Add content with proper spacing
                    content = chunk["content"].strip()
                    # Ensure content has proper formatting
                    if content:
                        # Add some basic markdown formatting improvements
                        content = content.replace('\n\n\n', '\n\n')  # Remove excessive line breaks
                        combined_parts.append(f"{content}\n\n")
                    
                    # Add separator between sections (except for last one)
                    if j < len(all_chunks) - 1:
                        combined_parts.append("---\n\n")
            
            # Add separator between documents (except for last one)
            if i < len(document_groups):
                combined_parts.append("\n" + "="*50 + "\n\n")
        
        return "".join(combined_parts)

    @staticmethod
    def _group_results_by_document(results: List[SearchResult]) -> Dict[str, List[SearchResult]]:
        """Group search results by document ID."""
        document_groups = {}
        
        for result in results:
            doc_id = result.document_id
            if doc_id not in document_groups:
                document_groups[doc_id] = []
            document_groups[doc_id].append(result)
        
        return document_groups

    @staticmethod
    def _format_document_group(
        title: str,
        source: str,
        metadata: Dict[str, Any],
        results: List[SearchResult],
    ) -> str:
        """Format a group of results from the same document."""
        # Document header
        markdown = f"## Document: {title} ({source})\n\n"
        
        # Document metadata (clean up for display)
        display_metadata = {k: v for k, v in metadata.items() 
                          if k not in ["title", "source", "original_filename"]}
        if display_metadata:
            markdown += f"**Metadata:** {json.dumps(display_metadata, indent=2)}\n\n"
        
        # Check if any result has full document in supporting context
        full_doc_result = None
        for result in results:
            for context in result.supporting_context:
                if context.type == "document":
                    full_doc_result = context
                    break
            if full_doc_result:
                break
        
        if full_doc_result:
            # Display full document
            markdown += "**Content:**\n"
            markdown += full_doc_result.document_content + "\n\n"
        else:
            # Display chunks
            markdown += "**Chunk Content:**\n\n"
            
            # Collect all unique chunks (from main results + supporting context)
            all_chunks = []
            chunk_ids_seen = set()
            
            for result in results:
                # Add main result chunk
                if result.id not in chunk_ids_seen:
                    all_chunks.append({
                        "id": result.id,
                        "content": result.page_content,
                        "metadata": result.metadata,
                        "is_matched": True,
                    })
                    chunk_ids_seen.add(result.id)
                
                # Add supporting chunks
                for context in result.supporting_context:
                    if context.type == "chunk" and context.chunk_id not in chunk_ids_seen:
                        all_chunks.append({
                            "id": context.chunk_id,
                            "content": context.chunk_content,
                            "metadata": context.chunk_metadata,
                            "is_matched": False,
                        })
                        chunk_ids_seen.add(context.chunk_id)
            
            # Sort chunks by chunk_index if available
            all_chunks.sort(key=lambda x: x["metadata"].get("chunk_index", 999999))
            
            # Format each chunk
            for chunk in all_chunks:
                chunk_index = chunk["metadata"].get("chunk_index", "?")
                match_indicator = " [MATCHED]" if chunk["is_matched"] else ""
                markdown += f"**Chunk {chunk_index}:{match_indicator}**\n"
                markdown += chunk["content"] + "\n\n"
        
        return markdown 