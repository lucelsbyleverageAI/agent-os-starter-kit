"""Search-related models and schemas."""

from datetime import datetime
from typing import Any, List, Union, Optional, Literal
from pydantic import BaseModel, Field


# =====================
# Search Query Models
# =====================

class SearchQuery(BaseModel):
    """Base search query model."""
    query: str = Field(..., description="Search query text")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results to return")
    filter: Optional[dict[str, Any]] = Field(None, description="Optional metadata filters")


class ContextualSearchQuery(SearchQuery):
    """Enhanced search query with contextual options."""
    return_surrounding_context: bool = Field(
        default=False, 
        description="Whether to include context around found chunks"
    )
    max_context_characters: int = Field(
        default=2000, 
        ge=100, 
        le=10000,
        description="Character limit for expanded context per result"
    )
    format_chunks_for_llm: bool = Field(
        default=False,
        description="Whether to format output in clean, hierarchical markdown"
    )


class KeywordSearchQuery(BaseModel):
    """Keyword search query model."""
    keywords: List[str] = Field(..., description="List of keywords or phrases to search for")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results to return")
    filter: Optional[dict[str, Any]] = Field(None, description="Optional metadata filters")
    return_surrounding_context: bool = Field(
        default=False, 
        description="Whether to include context around found chunks"
    )
    max_context_characters: int = Field(
        default=2000, 
        ge=100, 
        le=10000,
        description="Character limit for expanded context per result"
    )
    format_chunks_for_llm: bool = Field(
        default=False,
        description="Whether to format output in clean, hierarchical markdown"
    )


class HybridSearchQuery(BaseModel):
    """Hybrid search query combining semantic and keyword search."""
    query: str = Field(..., description="Semantic search query text")
    keywords: List[str] = Field(..., description="List of keywords or phrases to search for")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results to return")
    filter: Optional[dict[str, Any]] = Field(None, description="Optional metadata filters")
    return_surrounding_context: bool = Field(
        default=False, 
        description="Whether to include context around found chunks"
    )
    max_context_characters: int = Field(
        default=2000, 
        ge=100, 
        le=10000,
        description="Character limit for expanded context per result"
    )
    format_chunks_for_llm: bool = Field(
        default=False,
        description="Whether to format output in clean, hierarchical markdown"
    )
    semantic_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight for semantic search results (0.0-1.0, keyword weight = 1 - semantic_weight)"
    )


# =====================
# Supporting Context Objects
# =====================

class ChunkObject(BaseModel):
    """Represents a chunk in supporting context."""
    type: Literal["chunk"] = "chunk"
    chunk_id: str = Field(..., description="Unique chunk identifier")
    chunk_content: str = Field(..., description="Chunk text content")
    chunk_metadata: dict[str, Any] = Field(default_factory=dict, description="Chunk-level metadata")
    chunk_created_at: Optional[datetime] = Field(None, description="Chunk creation timestamp")
    chunk_updated_at: Optional[datetime] = Field(None, description="Chunk update timestamp")
    document_id: str = Field(..., description="Parent document identifier")
    document_metadata: dict[str, Any] = Field(default_factory=dict, description="Document-level metadata")


class DocumentObject(BaseModel):
    """Represents a full document in supporting context."""
    type: Literal["document"] = "document"
    document_id: str = Field(..., description="Unique document identifier")
    document_content: str = Field(..., description="Full document text content")
    document_metadata: dict[str, Any] = Field(default_factory=dict, description="Document-level metadata")
    document_created_at: Optional[datetime] = Field(None, description="Document creation timestamp")
    document_updated_at: Optional[datetime] = Field(None, description="Document update timestamp")


# Union type for supporting context
SupportingContext = Union[ChunkObject, DocumentObject]


# =====================
# Search Result Models
# =====================

class SearchResult(BaseModel):
    """Standard search result with optional supporting context."""
    id: str = Field(..., description="ID of the found chunk")
    page_content: str = Field(..., description="Content of the found chunk")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Chunk metadata")
    score: float = Field(..., description="Similarity score")
    document_id: str = Field(..., description="Parent document ID (always present)")
    document_metadata: dict[str, Any] = Field(
        default_factory=dict, 
        description="Document-level metadata (always present)"
    )
    supporting_context: List[SupportingContext] = Field(
        default_factory=list,
        description="Array of supporting chunks/documents (empty if no context requested)"
    )


class FormattedSearchResult(BaseModel):
    """LLM-formatted search result as markdown."""
    formatted_content: str = Field(..., description="Markdown-formatted content for LLM consumption")
    source_results: List[SearchResult] = Field(..., description="Original search results used to create this format")


class LLMSearchResponse(BaseModel):
    """Combined response with both formatted text and structured data for LLM usage."""
    formatted_text: str = Field(..., description="Single combined markdown text for easy LLM consumption")
    structured_results: List[SearchResult] = Field(..., description="Original structured search results with full metadata")
    total_found: int = Field(..., description="Total number of results found")
    query: str = Field(..., description="Original search query")
    contextual_options: dict[str, Any] = Field(default_factory=dict, description="Context expansion options used")


# =====================
# Search Response Models
# =====================

class SearchResponse(BaseModel):
    """Response wrapper for search results."""
    results: List[SearchResult] = Field(..., description="Search results")
    total_found: int = Field(..., description="Total number of results found")
    query: str = Field(..., description="Original search query")
    processing_time_ms: Optional[float] = Field(None, description="Processing time in milliseconds")


class FormattedSearchResponse(BaseModel):
    """Response wrapper for LLM-formatted search results."""
    formatted_results: List[FormattedSearchResult] = Field(..., description="LLM-formatted results")
    total_found: int = Field(..., description="Total number of results found") 
    query: str = Field(..., description="Original search query")
    processing_time_ms: Optional[float] = Field(None, description="Processing time in milliseconds")


# =====================
# Context Expansion Models
# =====================

class ContextExpansionConfig(BaseModel):
    """Configuration for context expansion logic."""
    max_characters: int = Field(default=2000, ge=100, le=10000)
    prefer_full_document: bool = Field(default=True, description="Prefer full document if under character limit")
    expansion_strategy: Literal["alternating", "sequential"] = Field(
        default="alternating",
        description="Strategy for expanding around found chunk"
    )


class ContextExpansionResult(BaseModel):
    """Result of context expansion for a single chunk."""
    original_chunk: SearchResult
    expanded_context: List[SupportingContext]
    context_type: Literal["full_document", "expanded_chunks", "none"]
    total_characters: int
    truncated: bool = Field(default=False, description="Whether context was truncated due to character limit") 