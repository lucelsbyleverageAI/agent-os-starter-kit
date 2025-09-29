"""Enhanced chunking service for intelligent document splitting."""

import logging
import re
from typing import List, Optional, Dict, Any
from langchain_core.documents import Document
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
    TextSplitter
)

logger = logging.getLogger(__name__)


class EnhancedChunkingService:
    """Service for intelligent document chunking with markdown awareness."""
    
    def __init__(self):
        """Initialize the chunking service."""
        # Default recursive character splitter (fallback)
        self.default_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        # Markdown header splitter for structured documents
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
                ("####", "Header 4"),
            ],
            strip_headers=False  # Keep headers for context
        )
        
        # Smaller chunks for better semantic search
        self.small_chunk_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        # Larger chunks for comprehensive context
        self.large_chunk_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=400,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
    
    async def chunk_documents(
        self, 
        documents: List[Document], 
        chunking_strategy: str = "markdown_aware",
        chunk_size: str = "medium",
        progress_callback: Optional[callable] = None
    ) -> List[Document]:
        """Chunk documents using the specified strategy.
        
        Args:
            documents: List of Document objects to chunk
            chunking_strategy: Strategy to use ('markdown_aware', 'recursive', 'semantic')
            chunk_size: Size preference ('small', 'medium', 'large')
            progress_callback: Optional progress callback
            
        Returns:
            List of chunked Document objects
        """
        if not documents:
            return []
        
        if progress_callback:
            progress_callback(f"Starting chunking with strategy: {chunking_strategy}")
        
        all_chunks = []
        
        for i, document in enumerate(documents):
            if progress_callback:
                progress_callback(f"Chunking document {i+1}/{len(documents)}")
            
            # Determine best chunking approach for this document
            chunks = await self._chunk_single_document(
                document, chunking_strategy, chunk_size
            )
            
            # Add chunk metadata
            for j, chunk in enumerate(chunks):
                chunk.metadata.update({
                    "chunk_index": j,
                    "total_chunks": len(chunks),
                    "chunking_strategy": chunking_strategy,
                    "chunk_size": chunk_size,
                    "source_document_index": i,
                })
            
            all_chunks.extend(chunks)
        
        if progress_callback:
            progress_callback(f"Chunking complete: {len(all_chunks)} chunks created")
        
        return all_chunks
    
    async def _chunk_single_document(
        self, 
        document: Document, 
        strategy: str, 
        chunk_size: str
    ) -> List[Document]:
        """Chunk a single document using the specified strategy.
        
        Args:
            document: Document to chunk
            strategy: Chunking strategy
            chunk_size: Chunk size preference
            
        Returns:
            List of chunked documents
        """
        # Choose splitter based on size preference
        base_splitter = self._get_base_splitter(chunk_size)
        
        if strategy == "markdown_aware":
            return await self._markdown_aware_chunking(document, base_splitter)
        elif strategy == "semantic":
            return await self._semantic_chunking(document, base_splitter)
        elif strategy == "recursive":
            return await self._recursive_chunking(document, base_splitter)
        else:
            logger.warning(f"Unknown chunking strategy: {strategy}, using recursive")
            return await self._recursive_chunking(document, base_splitter)
    
    def _get_base_splitter(self, chunk_size: str) -> TextSplitter:
        """Get the appropriate text splitter based on chunk size preference.
        
        Args:
            chunk_size: Size preference ('small', 'medium', 'large')
            
        Returns:
            Configured TextSplitter
        """
        if chunk_size == "small":
            return self.small_chunk_splitter
        elif chunk_size == "large":
            return self.large_chunk_splitter
        else:  # medium or default
            return self.default_splitter
    
    async def _markdown_aware_chunking(
        self, 
        document: Document, 
        base_splitter: TextSplitter
    ) -> List[Document]:
        """Chunk document with markdown structure awareness.
        
        Args:
            document: Document to chunk
            base_splitter: Fallback splitter for non-markdown content
            
        Returns:
            List of chunked documents
        """
        # Ensure we have valid content
        if not document or not hasattr(document, 'page_content'):
            logger.warning("Invalid document object passed to markdown chunking, falling back to recursive")
            return await self._recursive_chunking(document, base_splitter)
        
        content = document.page_content
        
        # Ensure content is a string
        if not isinstance(content, str):
            logger.warning(f"Document page_content is not a string (type: {type(content)}), falling back to recursive")
            return await self._recursive_chunking(document, base_splitter)
        
        # Check if document has markdown structure
        if self._has_markdown_structure(content):
            try:
                # Use markdown header splitter first - ensure we pass string content, not document
                header_chunks = self.markdown_splitter.split_text(content)
                
                # Create documents from header chunks
                markdown_docs = []
                for chunk in header_chunks:
                    # Ensure chunk is a string
                    if not isinstance(chunk, str):
                        logger.warning(f"Markdown splitter returned non-string chunk (type: {type(chunk)}), skipping")
                        continue
                        
                    chunk_doc = Document(
                        page_content=chunk,
                        metadata=document.metadata.copy()
                    )
                    markdown_docs.append(chunk_doc)
                
                # If no valid chunks were created, fall back to recursive
                if not markdown_docs:
                    logger.warning("No valid markdown chunks created, falling back to recursive")
                    return await self._recursive_chunking(document, base_splitter)
                
                # Further split large header chunks if needed
                final_chunks = []
                for chunk_doc in markdown_docs:
                    if len(chunk_doc.page_content) > base_splitter._chunk_size * 1.5:
                        # Split large header chunks
                        sub_chunks = base_splitter.split_documents([chunk_doc])
                        final_chunks.extend(sub_chunks)
                    else:
                        final_chunks.append(chunk_doc)
                
                return final_chunks
                
            except Exception as e:
                logger.warning(f"Markdown chunking failed: {e}, falling back to recursive")
                logger.debug(f"Content type: {type(content)}, Content length: {len(content) if isinstance(content, str) else 'N/A'}")
                logger.debug(f"Document metadata: {document.metadata}")
                return await self._recursive_chunking(document, base_splitter)
        else:
            # No markdown structure, use recursive chunking
            return await self._recursive_chunking(document, base_splitter)
    
    async def _semantic_chunking(
        self, 
        document: Document, 
        base_splitter: TextSplitter
    ) -> List[Document]:
        """Chunk document using semantic boundaries.
        
        Args:
            document: Document to chunk
            base_splitter: Base splitter for size control
            
        Returns:
            List of chunked documents
        """
        # For now, use enhanced recursive chunking with semantic separators
        # This could be extended with actual semantic analysis in the future
        content = document.page_content
        
        # Try to identify semantic boundaries
        semantic_separators = [
            "\n\n\n",  # Section breaks
            "\n\n",    # Paragraph breaks
            "\n",      # Line breaks
            ". ",      # Sentence breaks
            ", ",      # Clause breaks
            " ",       # Word breaks
            ""         # Character breaks
        ]
        
        # Create custom splitter with semantic separators
        semantic_splitter = RecursiveCharacterTextSplitter(
            chunk_size=base_splitter._chunk_size,
            chunk_overlap=base_splitter._chunk_overlap,
            length_function=len,
            separators=semantic_separators
        )
        
        return semantic_splitter.split_documents([document])
    
    async def _recursive_chunking(
        self, 
        document: Document, 
        base_splitter: TextSplitter
    ) -> List[Document]:
        """Chunk document using recursive character splitting.
        
        Args:
            document: Document to chunk
            base_splitter: Splitter to use
            
        Returns:
            List of chunked documents
        """
        return base_splitter.split_documents([document])
    
    def _has_markdown_structure(self, content: str) -> bool:
        """Check if content has markdown structure worth preserving.
        
        Args:
            content: Text content to check
            
        Returns:
            True if content has significant markdown structure
        """
        # Count markdown headers (including indented ones)
        header_count = len(re.findall(r'^\s*#{1,6}\s+', content, re.MULTILINE))
        
        # Check for other markdown elements
        has_lists = bool(re.search(r'^\s*[-*+]\s+', content, re.MULTILINE))
        has_code_blocks = bool(re.search(r'```', content))
        has_tables = bool(re.search(r'\|.*\|', content))
        
        # Consider it markdown if it has multiple headers or various markdown elements
        return header_count >= 2 or (header_count >= 1 and (has_lists or has_code_blocks or has_tables))
    
    def optimize_chunks_for_retrieval(self, chunks: List[Document]) -> List[Document]:
        """Optimize chunks for better retrieval performance.
        
        Args:
            chunks: List of chunked documents
            
        Returns:
            Optimized list of chunks (always at least one chunk)
        """
        if not chunks:
            return []
        
        optimized_chunks = []
        
        for chunk in chunks:
            # Skip chunks that are too small (less than 50 characters)
            if len(chunk.page_content.strip()) < 50:
                continue
            
            # Merge very small chunks with next chunk if possible
            if (len(chunk.page_content.strip()) < 200 and 
                optimized_chunks and 
                len(optimized_chunks[-1].page_content) < 800):
                
                # Merge with previous chunk
                prev_chunk = optimized_chunks[-1]
                prev_chunk.page_content += "\n\n" + chunk.page_content
                prev_chunk.metadata["merged_chunks"] = prev_chunk.metadata.get("merged_chunks", 0) + 1
                
            else:
                # Add chunk processing metadata
                chunk.metadata.update({
                    "content_length": len(chunk.page_content),
                    "word_count": len(chunk.page_content.split()),
                    "processed_at": "enhanced_chunking",
                })
                
                optimized_chunks.append(chunk)
        
        # CRITICAL FIX: Always ensure at least one chunk exists
        # This prevents NotNullViolation errors when all chunks are filtered out
        if not optimized_chunks and chunks:
            # If no chunks survived optimization, keep the largest original chunk
            # or the first chunk if all are the same size
            best_chunk = max(chunks, key=lambda x: len(x.page_content.strip()))
            
            # Add processing metadata to the preserved chunk
            best_chunk.metadata.update({
                "content_length": len(best_chunk.page_content),
                "word_count": len(best_chunk.page_content.split()),
                "processed_at": "enhanced_chunking",
                "preserved_small_chunk": True,  # Flag to indicate this was a small chunk we kept
                "original_chunk_count": len(chunks),
            })
            
            optimized_chunks.append(best_chunk)
            
            logger.info(f"Preserved small chunk ({len(best_chunk.page_content)} chars) to prevent empty document")
        
        return optimized_chunks
    
    def get_chunking_stats(self, chunks: List[Document]) -> Dict[str, Any]:
        """Get statistics about the chunking results.
        
        Args:
            chunks: List of chunked documents
            
        Returns:
            Dictionary with chunking statistics
        """
        if not chunks:
            return {
                "total_chunks": 0,
                "total_characters": 0,
                "total_words": 0,
                "average_chunk_size": 0,
                "min_chunk_size": 0,
                "max_chunk_size": 0,
            }
        
        chunk_sizes = [len(chunk.page_content) for chunk in chunks]
        word_counts = [len(chunk.page_content.split()) for chunk in chunks]
        
        return {
            "total_chunks": len(chunks),
            "total_characters": sum(chunk_sizes),
            "total_words": sum(word_counts),
            "average_chunk_size": sum(chunk_sizes) // len(chunk_sizes),
            "min_chunk_size": min(chunk_sizes),
            "max_chunk_size": max(chunk_sizes),
            "average_word_count": sum(word_counts) // len(word_counts),
            "chunking_strategy": chunks[0].metadata.get("chunking_strategy", "unknown"),
        } 