"""Agent file system API endpoints for collection and document operations."""

import difflib
import json
import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from langconnect.auth import resolve_user_or_service, AuthenticatedActor, ServiceAccount
from langconnect.database.collections import CollectionsManager, Collection
from langconnect.database.document import DocumentManager
from langconnect.database.permissions import (
    get_user_accessible_collections,
    verify_collection_permission,
    get_user_collection_permission
)
from langconnect.services.job_service import job_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent-filesystem", tags=["Agent File System"])


# ==================== Request/Response Models ====================

class CollectionInfo(BaseModel):
    """Collection information model."""
    collection_id: str
    name: str
    description: Optional[str] = None
    document_count: int
    total_size_bytes: int
    created_at: str
    updated_at: str
    permission_level: str


class CollectionListResponse(BaseModel):
    """Response model for listing collections."""
    collections: List[CollectionInfo]


class FileInfo(BaseModel):
    """File information model."""
    document_id: str
    collection_id: str
    collection_name: str
    name: str
    description: Optional[str] = None
    size_bytes: int
    size_lines: int
    chunk_count: int
    created_at: str
    updated_at: str
    source_type: Optional[str] = None


class FileListResponse(BaseModel):
    """Response model for listing files."""
    files: List[FileInfo]
    total: int
    limit: int
    offset: int


class FileContent(BaseModel):
    """File content model."""
    document_id: str
    collection_id: str
    collection_name: str
    document_name: str
    content: str
    total_lines: int
    total_bytes: int
    line_range: dict
    truncated: bool
    format: str


class SearchMatch(BaseModel):
    """Search match model for grep results."""
    document_id: str
    collection_id: str
    collection_name: str
    document_name: str
    line_number: int
    line_content: str
    context_before: Optional[List[str]] = None
    context_after: Optional[List[str]] = None


class SearchRequest(BaseModel):
    """Request model for searching files."""
    pattern: str = Field(..., description="Regex pattern to search for")
    collection_id: Optional[str] = Field(None, description="Optional collection ID filter")
    document_ids: Optional[List[str]] = Field(None, description="Optional document ID filters")
    case_sensitive: bool = Field(False, description="Case sensitive search")
    max_results: int = Field(100, ge=1, le=500, description="Maximum results")
    context_lines: int = Field(2, ge=0, le=10, description="Context lines before/after")
    scoped_collections: Optional[List[str]] = Field(None, description="Collection IDs from agent config")


class HybridSearchRequest(BaseModel):
    """Request model for hybrid search across collections."""
    query: str = Field(..., description="Semantic search query")
    keywords: Optional[List[str]] = Field(None, description="Optional keywords for hybrid search")
    collection_id: Optional[str] = Field(None, description="Optional collection ID filter")
    limit: int = Field(5, ge=1, le=20, description="Maximum results")
    return_surrounding_context: bool = Field(True, description="Include surrounding context")
    max_context_characters: int = Field(2500, ge=0, le=10000, description="Max context characters")
    format_chunks_for_llm: bool = Field(True, description="Format results for LLM consumption")
    semantic_weight: float = Field(0.6, ge=0.0, le=1.0, description="Weight for semantic search (0-1)")
    scoped_collections: List[str] = Field(..., description="Collection IDs from agent config")


class SearchResponse(BaseModel):
    """Response model for search results."""
    matches: List[SearchMatch]
    total_matches: int
    total_files_searched: int
    truncated: bool


class CreateFileRequest(BaseModel):
    """Request model for creating a new file."""
    name: str = Field(..., description="File name")
    content: str = Field(..., description="File content")
    metadata: Optional[dict] = Field(default_factory=dict, description="Additional metadata")
    scoped_collections: Optional[List[str]] = Field(None, description="Collection IDs from agent config")


class CreateFileResponse(BaseModel):
    """Response model for file creation."""
    document_id: str
    collection_id: str
    name: str
    size_bytes: int
    size_lines: int
    processing_status: str
    message: str


class EditFileRequest(BaseModel):
    """Request model for editing a file."""
    collection_id: Optional[str] = Field(None, description="Optional collection ID for validation")
    old_string: str = Field(..., description="Exact text to find and replace")
    new_string: str = Field(..., description="Replacement text")
    replace_all: bool = Field(False, description="Replace all occurrences")
    scoped_collections: Optional[List[str]] = Field(None, description="Collection IDs from agent config")


class EditFileResponse(BaseModel):
    """Response model for file edit."""
    success: bool
    changes_made: Optional[int] = None
    document_id: str
    collection_id: str
    preview: Optional[str] = None
    processing_status: Optional[str] = None
    message: str
    error: Optional[str] = None
    occurrences: Optional[int] = None
    suggestion: Optional[str] = None


class DeleteFileResponse(BaseModel):
    """Response model for file deletion."""
    success: bool
    document_id: str
    collection_id: str
    document_name: str
    chunks_deleted: int
    message: str


# ==================== Helper Functions ====================

def get_user_id_from_actor(actor: AuthenticatedActor, user_id_override: Optional[str] = None) -> str:
    """
    Extract user ID from authenticated actor.
    
    For service accounts (n8n, Zapier, etc.), a user_id must be provided in the request
    to specify which user's permissions to check. For regular users, uses the authenticated
    user's ID.
    
    Args:
        actor: The authenticated actor (user or service account)
        user_id_override: Optional user_id from request (required for service accounts)
        
    Returns:
        str: The user ID to use for permissions checks
        
    Raises:
        HTTPException: If service account doesn't provide user_id
    """
    if isinstance(actor, ServiceAccount):
        if not user_id_override:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service accounts must provide 'user_id' parameter to specify the user context"
            )
        return user_id_override
    else:
        # Regular authenticated user
        return actor.user_id


def generate_unified_diff(old_content: str, new_content: str, filename: str) -> str:
    """Generate git-style unified diff."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=""
    )
    
    return "".join(diff)


# ==================== Endpoints ====================

@router.get("/collections", response_model=CollectionListResponse)
async def list_collections(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    scoped_collections: Optional[str] = Query(None, description="Comma-separated list of collection IDs from agent config"),
    user_id: Optional[str] = Query(None, description="User ID (required for service accounts)"),
):
    """List all accessible collections with metadata.
    
    Returns collections the user has access to along with document counts,
    sizes, and permission levels. If scoped_collections is provided, filters
    to only those collections (intersection of agent config and user permissions).
    
    For service accounts (n8n, Zapier), user_id must be provided in query parameters.
    """
    resolved_user_id = get_user_id_from_actor(actor, user_id)
    
    try:
        # Get all accessible collections (user-level permissions)
        accessible_collections = await get_user_accessible_collections(resolved_user_id, "viewer")
        
        if not accessible_collections:
            return CollectionListResponse(collections=[])
        
        # Parse scoped collections from agent config
        scoped_collection_ids = set()
        if scoped_collections:
            scoped_collection_ids = {cid.strip() for cid in scoped_collections.split(",") if cid.strip()}
        
        # Filter to intersection of agent config and user permissions
        if scoped_collection_ids:
            accessible_collections = {
                cid: perm for cid, perm in accessible_collections.items()
                if cid in scoped_collection_ids
            }

        if not accessible_collections:
            return CollectionListResponse(collections=[])
        
        # Fetch collection details
        collections_manager = CollectionsManager(resolved_user_id)
        all_collections = await collections_manager.list()
        
        result_collections = []
        
        for coll in all_collections:
            collection_id = coll["uuid"]
            
            # Skip if not in accessible collections (after scoping)
            if collection_id not in accessible_collections:
                continue
            
            # Get document statistics
            from langconnect.database.connection import get_db_connection
            async with get_db_connection() as conn:
                stats_query = """
                    SELECT 
                        COUNT(*) as document_count,
                        COALESCE(SUM(LENGTH(content)), 0) as total_size_bytes,
                        MAX(updated_at) as updated_at
                    FROM langconnect.langchain_pg_document
                    WHERE collection_id = $1
                """
                stats = await conn.fetchrow(stats_query, collection_id)
            
            collection_info = CollectionInfo(
                collection_id=collection_id,
                name=coll["name"],
                description=coll.get("metadata", {}).get("description"),
                document_count=stats["document_count"] or 0,
                total_size_bytes=stats["total_size_bytes"] or 0,
                created_at=coll.get("created_at", ""),
                updated_at=stats["updated_at"].isoformat() if stats["updated_at"] else coll.get("updated_at", ""),
                permission_level=accessible_collections[collection_id]
            )
            result_collections.append(collection_info)
        
        return CollectionListResponse(collections=result_collections)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list collections: {str(e)}"
        )


@router.get("/files", response_model=FileListResponse)
async def list_files(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: Optional[str] = Query(None, description="Filter to specific collection"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    sort_by: str = Query("updated_at", description="Sort field"),
    order: str = Query("desc", description="Sort order (asc/desc)"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    scoped_collections: Optional[str] = Query(None, description="Comma-separated list of collection IDs from agent config"),
    user_id: Optional[str] = Query(None, description="User ID (required for service accounts)"),
):
    """List documents across accessible collections.
    
    Returns paginated list of documents with metadata like size, line count, and chunk count.
    If scoped_collections is provided, filters to only those collections.
    
    For service accounts (n8n, Zapier), user_id must be provided in query parameters.
    """
    
    resolved_user_id = get_user_id_from_actor(actor, user_id)
    
    try:
        # Get accessible collections (user-level permissions)
        accessible_collections = await get_user_accessible_collections(resolved_user_id, "viewer")
        
        if not accessible_collections:
            return FileListResponse(files=[], total=0, limit=limit, offset=offset)
        
        # Parse scoped collections from agent config
        scoped_collection_ids = set()
        if scoped_collections:
            scoped_collection_ids = {cid.strip() for cid in scoped_collections.split(",") if cid.strip()}
        else:
            logger.info(f"[FS_LIST_FILES] No scoped_collections provided, using all accessible collections")
        # Filter to intersection of agent config and user permissions
        if scoped_collection_ids:
            accessible_collections = {
                cid: perm for cid, perm in accessible_collections.items()
                if cid in scoped_collection_ids
            }
        
        if not accessible_collections:
            return FileListResponse(files=[], total=0, limit=limit, offset=offset)
        
        # Filter to specific collection if requested
        target_collections = []
        if collection_id:
            if collection_id not in accessible_collections:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this collection"
                )
            target_collections = [collection_id]
        else:
            target_collections = list(accessible_collections.keys())
        
        # Query documents
        from langconnect.database.connection import get_db_connection
        async with get_db_connection() as conn:
            # Build query with filters
            source_filter = ""
            params = [target_collections, limit, offset]
            if source_type:
                source_filter = "AND d.cmetadata->>'source_type' = $4"
                params.append(source_type)
            
            # Validate and normalize sort parameters
            valid_sort_fields = {"created_at", "updated_at", "name", "size"}
            sort_field = sort_by if sort_by in valid_sort_fields else "updated_at"
            sort_order = "DESC" if order.lower() == "desc" else "ASC"
            
            if sort_field == "name":
                sort_clause = f"""
                    COALESCE(
                        d.cmetadata->>'title',
                        d.cmetadata->>'original_filename',
                        d.cmetadata->>'source_name'
                    ) {sort_order}
                """
            elif sort_field == "size":
                sort_clause = f"LENGTH(d.content) {sort_order}"
            else:
                sort_clause = f"d.{sort_field} {sort_order}"
            
            query = f"""
                SELECT 
                    d.id as document_id,
                    d.collection_id,
                    c.name as collection_name,
                    COALESCE(
                        d.cmetadata->>'title',
                        d.cmetadata->>'original_filename',
                        d.cmetadata->>'source_name'
                    ) as name,
                    d.cmetadata->>'description' as description,
                    LENGTH(d.content) as size_bytes,
                    (LENGTH(d.content) - LENGTH(REPLACE(d.content, E'\n', ''))) + 1 as size_lines,
                    (
                        SELECT COUNT(*) 
                        FROM langconnect.langchain_pg_embedding e 
                        WHERE e.document_id = d.id
                    ) as chunk_count,
                    d.created_at,
                    d.updated_at,
                    d.cmetadata->>'source_type' as source_type
                FROM langconnect.langchain_pg_document d
                INNER JOIN langconnect.langchain_pg_collection c ON d.collection_id = c.uuid
                WHERE d.collection_id = ANY($1::uuid[])
                  {source_filter}
                ORDER BY {sort_clause}
                LIMIT $2 OFFSET $3;
            """
            
            rows = await conn.fetch(query, *params)
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*) as total
                FROM langconnect.langchain_pg_document d
                WHERE d.collection_id = ANY($1::uuid[])
                  {source_filter}
            """
            count_params = [target_collections]
            if source_type:
                count_params.append(source_type)
            total_row = await conn.fetchrow(count_query, *count_params)
            total = total_row["total"] if total_row else 0
        
        files = []
        for row in rows:
            files.append(FileInfo(
                document_id=str(row["document_id"]),
                collection_id=str(row["collection_id"]),
                collection_name=row["collection_name"],
                name=row["name"] or "Untitled",
                description=row["description"] or None,
                size_bytes=row["size_bytes"] or 0,
                size_lines=row["size_lines"] or 0,
                chunk_count=row["chunk_count"] or 0,
                created_at=row["created_at"].isoformat() if row["created_at"] else "",
                updated_at=row["updated_at"].isoformat() if row["updated_at"] else "",
                source_type=row["source_type"]
            ))
        
        return FileListResponse(
            files=files,
            total=total,
            limit=limit,
            offset=offset
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}"
        )


@router.get("/files/{document_id}", response_model=FileContent)
async def read_file(
    document_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: Optional[str] = Query(None, description="Optional collection ID for validation"),
    offset: int = Query(0, ge=0, description="Starting line number (0-indexed)"),
    limit: int = Query(2000, ge=1, le=5000, description="Number of lines to return"),
    include_line_numbers: bool = Query(True, description="Include line numbers in output"),
    scoped_collections: Optional[str] = Query(None, description="Comma-separated list of collection IDs from agent config"),
    user_id: Optional[str] = Query(None, description="User ID (required for service accounts)"),
):
    """Read document content with line numbers.
    
    Returns formatted document content with optional line numbers and pagination support.
    If scoped_collections is provided, enforces that the document belongs to a scoped collection.
    
    For service accounts (n8n, Zapier), user_id must be provided in query parameters.
    """
    resolved_user_id = get_user_id_from_actor(actor, user_id)
    
    try:
        # First get the document to find its collection
        from langconnect.database.connection import get_db_connection
        async with get_db_connection() as conn:
            doc_query = """
                SELECT collection_id
                FROM langconnect.langchain_pg_document
                WHERE id = $1
            """
            doc_row = await conn.fetchrow(doc_query, document_id)
            
            if not doc_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )
            
            actual_collection_id = str(doc_row["collection_id"])
        
        # Parse scoped collections from agent config
        if scoped_collections:
            scoped_collection_ids = {cid.strip() for cid in scoped_collections.split(",") if cid.strip()}
            if actual_collection_id not in scoped_collection_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Document does not belong to an accessible collection in this agent's scope"
                )
        
        # Verify collection access
        if collection_id and collection_id != actual_collection_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document does not belong to specified collection"
            )
        
        has_permission = await verify_collection_permission(resolved_user_id, actual_collection_id, "viewer")
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to read this document"
            )
        
        # Get document content with lines
        doc_manager = DocumentManager(actual_collection_id, resolved_user_id)
        result = await doc_manager.get_document_with_lines(
            document_id,
            offset=offset,
            limit=limit,
            include_line_numbers=include_line_numbers
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or empty"
            )
        
        # Get collection name
        collections_manager = CollectionsManager(resolved_user_id)
        collection = await collections_manager.get(actual_collection_id)
        collection_name = collection["name"] if collection else "Unknown"
        
        response = FileContent(
            document_id=document_id,
            collection_id=actual_collection_id,
            collection_name=collection_name,
            document_name=result["document_name"],
            content=result["content"],
            total_lines=result["total_lines"],
            total_bytes=result["total_bytes"],
            line_range=result["line_range"],
            truncated=result["truncated"],
            format="line_numbered" if include_line_numbers else "plain"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[FS_READ_FILE] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read file: {str(e)}"
        )


@router.post("/files/search", response_model=SearchResponse)
async def search_files(
    request: SearchRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    user_id: Optional[str] = Query(None, description="User ID (required for service accounts)"),
):
    """Search for patterns across files using regex (grep-like functionality).
    
    Searches document content for regex patterns and returns matching lines with context.
    If scoped_collections is provided in request, filters to only those collections.
    
    For service accounts (n8n, Zapier), user_id must be provided in query parameters.
    """
    resolved_user_id = get_user_id_from_actor(actor, user_id)
    
    try:
        # Get accessible collections (user-level permissions)
        accessible_collections = await get_user_accessible_collections(resolved_user_id, "viewer")
        
        if not accessible_collections:
            return SearchResponse(
                matches=[],
                total_matches=0,
                total_files_searched=0,
                truncated=False
            )
        
        # Filter to scoped collections from agent config
        if request.scoped_collections:
            accessible_collections = {
                cid: perm for cid, perm in accessible_collections.items()
                if cid in request.scoped_collections
            }
            logger.info(f"[FS_GREP] Filtered to {len(accessible_collections)} scoped collections")
        
        if not accessible_collections:
            return SearchResponse(
                matches=[],
                total_matches=0,
                total_files_searched=0,
                truncated=False
            )
        
        # Filter to specific collection if requested
        target_collections = []
        if request.collection_id:
            if request.collection_id not in accessible_collections:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this collection"
                )
            target_collections = [request.collection_id]
        else:
            target_collections = list(accessible_collections.keys())
        
        # Perform search across collections
        all_matches = []
        files_searched = 0
        
        for coll_id in target_collections:
            doc_manager = DocumentManager(coll_id, resolved_user_id)
            matches = await doc_manager.search_documents_by_pattern(
                pattern=request.pattern,
                case_sensitive=request.case_sensitive,
                max_results=request.max_results - len(all_matches),
                context_lines=request.context_lines,
                document_ids=request.document_ids
            )
            
            # Get collection name
            collections_manager = CollectionsManager(resolved_user_id)
            collection = await collections_manager.get(coll_id)
            collection_name = collection["name"] if collection else "Unknown"
            
            # Add collection name to matches
            for match in matches:
                match["collection_name"] = collection_name
                all_matches.append(SearchMatch(**match))
            
            # Count files searched
            from langconnect.database.connection import get_db_connection
            async with get_db_connection() as conn:
                count_query = """
                    SELECT COUNT(DISTINCT id) as count
                    FROM langconnect.langchain_pg_document
                    WHERE collection_id = $1
                """
                count_row = await conn.fetchrow(count_query, coll_id)
                files_searched += count_row["count"] if count_row else 0
            
            # Stop if we've reached max results
            if len(all_matches) >= request.max_results:
                break
        
        truncated = len(all_matches) >= request.max_results
        
        logger.info(f"[FS_GREP] Found {len(all_matches)} matches across {files_searched} files")
        return SearchResponse(
            matches=all_matches,
            total_matches=len(all_matches),
            total_files_searched=files_searched,
            truncated=truncated
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[FS_GREP] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search files: {str(e)}"
        )


@router.post("/search")
async def hybrid_search(
    request: HybridSearchRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    user_id: Optional[str] = Query(None, description="User ID (required for service accounts)"),
):
    """Hybrid search across collections using semantic + keyword search.
    
    Performs hybrid search combining semantic similarity and keyword matching.
    Returns LLM-formatted results with document citations.
    Enforces scoped_collections from agent config.
    
    For service accounts (n8n, Zapier), user_id must be provided in query parameters.
    """
    resolved_user_id = get_user_id_from_actor(actor, user_id)
    logger.info(f"[HYBRID_SEARCH] user_id={resolved_user_id}, query={request.query[:50]}, collection_id={request.collection_id}, scoped={len(request.scoped_collections)}")
    
    try:
        # Get accessible collections (user-level permissions)
        accessible_collections = await get_user_accessible_collections(resolved_user_id, "viewer")
        
        if not accessible_collections:
            return {
                "formatted_text": "No accessible collections found.",
                "structured_results": []
            }
        
        # Filter to scoped collections from agent config (CRITICAL SECURITY CHECK)
        if request.scoped_collections:
            accessible_collections = {
                cid: perm for cid, perm in accessible_collections.items()
                if cid in request.scoped_collections
            }
            logger.info(f"[HYBRID_SEARCH] Filtered to {len(accessible_collections)} scoped collections")
        
        if not accessible_collections:
            return {
                "formatted_text": "No accessible collections in agent scope.",
                "structured_results": []
            }
        
        # Filter to specific collection if requested
        target_collections = []
        if request.collection_id:
            if request.collection_id not in accessible_collections:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have access to this collection"
                )
            target_collections = [request.collection_id]
        else:
            target_collections = list(accessible_collections.keys())
        
        # Perform hybrid search across target collections
        # We'll aggregate results from all collections
        all_formatted_texts = []
        all_structured_results = []
        unique_documents = {}
        
        for coll_id in target_collections:
            try:
                # Create collection instance
                collection = Collection(coll_id, resolved_user_id)
                
                # Get collection name
                collections_manager = CollectionsManager(resolved_user_id)
                collection_data = await collections_manager.get(coll_id)
                collection_name = collection_data["name"] if collection_data else "Unknown"
                
                # Perform hybrid search (returns LLMSearchResponse)
                results = await collection.hybrid_search(
                    query=request.query,
                    keywords=request.keywords or [],
                    limit=min(request.limit, 20),
                    filter=None,
                    return_surrounding_context=request.return_surrounding_context,
                    max_context_characters=request.max_context_characters,
                    format_chunks_for_llm=request.format_chunks_for_llm,
                    semantic_weight=request.semantic_weight,
                )
                
                # Add formatted text if available
                if results.formatted_text:
                    all_formatted_texts.append(f"## Results from {collection_name}\n\n{results.formatted_text}")
                
                # Add structured results with collection name
                for result in results.structured_results:
                    result_dict = result.model_dump() if hasattr(result, 'model_dump') else result.dict()
                    result_dict["collection_name"] = collection_name
                    all_structured_results.append(result_dict)
                    
                    # Track unique documents
                    doc_id = result.document_id
                    if doc_id and doc_id not in unique_documents:
                        unique_documents[doc_id] = {
                            "document_id": doc_id,
                            "collection_name": collection_name,
                            "title": result.document_metadata.get("title", "Untitled") if result.document_metadata else "Untitled",
                            "source_name": (result.document_metadata.get("source_name") or 
                                          result.document_metadata.get("original_filename", "Unknown source")) if result.document_metadata else "Unknown source",
                        }
                
                # Stop if we've reached limit
                if len(all_structured_results) >= request.limit:
                    break
                    
            except Exception as e:
                logger.warning(f"[HYBRID_SEARCH] Failed to search collection {coll_id}: {e}")
                continue
        
        # Limit total results
        all_structured_results = all_structured_results[:request.limit]
        
        # Combine formatted text from all collections
        combined_formatted_text = "\n\n---\n\n".join(all_formatted_texts) if all_formatted_texts else "No results found."
        
        # Return in same format as collection.hybrid_search
        return {
            "formatted_text": combined_formatted_text,
            "structured_results": all_structured_results,
            "documents": list(unique_documents.values())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[HYBRID_SEARCH] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform hybrid search: {str(e)}"
        )


@router.post("/collections/{collection_id}/files", response_model=CreateFileResponse)
async def create_file(
    collection_id: str,
    request: CreateFileRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    user_id: Optional[str] = Query(None, description="User ID (required for service accounts)"),
):
    """Create a new document in a collection.
    
    Creates a new document and queues it for chunking and embedding.
    Requires editor or owner permission on the collection.
    If scoped_collections is provided, verifies the collection is in scope.
    
    For service accounts (n8n, Zapier), user_id must be provided in query parameters.
    """
    resolved_user_id = get_user_id_from_actor(actor, user_id)
    logger.info(f"[FS_CREATE_FILE] user_id={resolved_user_id}, collection_id={collection_id}, scoped={request.scoped_collections}, name={request.name}")
    
    try:
        # Check scoped collections from agent config
        if request.scoped_collections and collection_id not in request.scoped_collections:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Collection is not in this agent's scope"
            )
        
        # Verify editor or owner permission
        has_permission = await verify_collection_permission(resolved_user_id, collection_id, "editor")
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Creating files requires editor or owner permission"
            )
        
        # Create document
        doc_manager = DocumentManager(collection_id, resolved_user_id)
        metadata = {
            "title": request.name,
            "source_type": "agent_created",
            "created_by": resolved_user_id,
            "processing_status": "pending",
            **request.metadata
        }
        
        document_id = await doc_manager.create_document(
            content=request.content,
            metadata=metadata
        )
        
        # Calculate metrics
        size_bytes = len(request.content)
        size_lines = request.content.count("\n") + 1
        
        # Queue document for processing (chunking and embedding)
        try:
            job_id = await job_service.queue_document_reprocessing(
                document_id=document_id,
                collection_id=collection_id,
                user_id=resolved_user_id
            )
            logger.info(f"[FS_CREATE_FILE] Queued processing job {job_id} for new document {document_id}")
        except Exception as e:
            logger.error(f"[FS_CREATE_FILE] Failed to queue processing job: {e}")
            # Don't fail the request if job queuing fails - document is still created
        
        logger.info(f"[FS_CREATE_FILE] Created document {document_id}")
        return CreateFileResponse(
            document_id=document_id,
            collection_id=collection_id,
            name=request.name,
            size_bytes=size_bytes,
            size_lines=size_lines,
            processing_status="processing",
            message="Document created successfully."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[FS_CREATE_FILE] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create file: {str(e)}"
        )


@router.patch("/files/{document_id}", response_model=EditFileResponse)
async def edit_file(
    document_id: str,
    request: EditFileRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    user_id: Optional[str] = Query(None, description="User ID (required for service accounts)"),
):
    """Edit document content using string replacement.
    
    Replaces old_string with new_string in the document content.
    Requires editor or owner permission on the collection.
    If scoped_collections is provided, verifies the document's collection is in scope.
    
    For service accounts (n8n, Zapier), user_id must be provided in query parameters.
    """
    resolved_user_id = get_user_id_from_actor(actor, user_id)
    logger.info(f"[FS_EDIT_FILE] user_id={resolved_user_id}, document_id={document_id}, scoped={request.scoped_collections}, replace_all={request.replace_all}")
    
    try:
        # Get document to find its collection
        from langconnect.database.connection import get_db_connection
        async with get_db_connection() as conn:
            doc_query = """
                SELECT collection_id
                FROM langconnect.langchain_pg_document
                WHERE id = $1
            """
            doc_row = await conn.fetchrow(doc_query, document_id)
            
            if not doc_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )
            
            actual_collection_id = str(doc_row["collection_id"])
        
        # Check scoped collections from agent config
        if request.scoped_collections and actual_collection_id not in request.scoped_collections:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Document does not belong to a collection in this agent's scope"
            )
        
        # Verify collection access
        if request.collection_id and request.collection_id != actual_collection_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document does not belong to specified collection"
            )
        
        # Verify editor permission
        has_permission = await verify_collection_permission(resolved_user_id, actual_collection_id, "editor")
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Editing files requires editor or owner permission"
            )
        
        # Get current document
        doc_manager = DocumentManager(actual_collection_id, resolved_user_id)
        doc = await doc_manager.get_document(document_id)
        
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        content = doc["content"]
        
        # Validate old_string exists
        if request.old_string not in content:
            return EditFileResponse(
                success=False,
                document_id=document_id,
                collection_id=actual_collection_id,
                message="The specified text was not found in the document",
                error="string_not_found",
                suggestion="Use fs_read_file to view current content, then try again with exact text"
            )
        
        # Check for ambiguity if not replace_all
        if not request.replace_all:
            count = content.count(request.old_string)
            if count > 1:
                return EditFileResponse(
                    success=False,
                    document_id=document_id,
                    collection_id=actual_collection_id,
                    message=f"Text appears {count} times in document",
                    error="ambiguous_match",
                    occurrences=count,
                    suggestion="Include more surrounding context in old_string, or set replace_all=true"
                )
        
        # Perform replacement
        if request.replace_all:
            new_content = content.replace(request.old_string, request.new_string)
            changes = content.count(request.old_string)
        else:
            new_content = content.replace(request.old_string, request.new_string, 1)
            changes = 1
        
        # Generate diff preview
        document_name = (
            doc.get("metadata", {}).get("title") or 
            doc.get("metadata", {}).get("original_filename") or 
            "document"
        )
        preview = generate_unified_diff(content, new_content, document_name)
        
        # Update document
        success = await doc_manager.update_document_content(document_id, new_content)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update document"
            )
        
        # Queue re-processing job to update embeddings
        try:
            job_id = await job_service.queue_document_reprocessing(
                document_id=document_id,
                collection_id=actual_collection_id,
                user_id=resolved_user_id
            )
            logger.info(f"[FS_EDIT_FILE] Queued reprocessing job {job_id} for updated document {document_id}")
        except Exception as e:
            logger.error(f"[FS_EDIT_FILE] Failed to queue reprocessing job: {e}")
            # Don't fail the request if job queuing fails - document is still updated
        
        logger.info(f"[FS_EDIT_FILE] Updated document {document_id} with {changes} changes")
        return EditFileResponse(
            success=True,
            changes_made=changes,
            document_id=document_id,
            collection_id=actual_collection_id,
            preview=preview,
            processing_status="processing",
            message="Document updated."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[FS_EDIT_FILE] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit file: {str(e)}"
        )


@router.delete("/files/{document_id}", response_model=DeleteFileResponse)
async def delete_file(
    document_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: Optional[str] = Query(None, description="Optional collection ID for validation"),
    scoped_collections: Optional[str] = Query(None, description="Comma-separated list of collection IDs from agent config"),
    user_id: Optional[str] = Query(None, description="User ID (required for service accounts)"),
):
    """Delete a document from a collection.
    
    Permanently deletes the document and all associated chunks/embeddings.
    Requires owner permission on the collection.
    If scoped_collections is provided, verifies the document's collection is in scope.
    
    For service accounts (n8n, Zapier), user_id must be provided in query parameters.
    """
    resolved_user_id = get_user_id_from_actor(actor, user_id)
    logger.info(f"[FS_DELETE_FILE] user_id={resolved_user_id}, document_id={document_id}, scoped={scoped_collections}")
    
    try:
        # Get document to find its collection
        from langconnect.database.connection import get_db_connection
        async with get_db_connection() as conn:
            doc_query = """
                SELECT collection_id, cmetadata
                FROM langconnect.langchain_pg_document
                WHERE id = $1
            """
            doc_row = await conn.fetchrow(doc_query, document_id)
            
            if not doc_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )
            
            actual_collection_id = str(doc_row["collection_id"])
            metadata = json.loads(doc_row["cmetadata"]) if doc_row["cmetadata"] else {}
        
        # Check scoped collections from agent config
        if scoped_collections:
            scoped_collection_ids = {cid.strip() for cid in scoped_collections.split(",") if cid.strip()}
            if actual_collection_id not in scoped_collection_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Document does not belong to a collection in this agent's scope"
                )
        
        # Verify collection access
        if collection_id and collection_id != actual_collection_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document does not belong to specified collection"
            )
        
        # Verify owner permission (delete requires owner)
        has_permission = await verify_collection_permission(resolved_user_id, actual_collection_id, "owner")
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Deleting files requires owner permission"
            )
        
        # Count chunks before deletion
        doc_manager = DocumentManager(actual_collection_id, resolved_user_id)
        async with get_db_connection() as conn:
            chunk_query = """
                SELECT COUNT(*) as count
                FROM langconnect.langchain_pg_embedding
                WHERE document_id = $1 AND collection_id = $2
            """
            chunk_row = await conn.fetchrow(chunk_query, document_id, actual_collection_id)
            chunk_count = chunk_row["count"] if chunk_row else 0
        
        # Delete document (embeddings should cascade or be handled separately)
        async with get_db_connection() as conn:
            # Delete embeddings first
            delete_embeddings_query = """
                DELETE FROM langconnect.langchain_pg_embedding
                WHERE document_id = $1 AND collection_id = $2
            """
            await conn.execute(delete_embeddings_query, document_id, actual_collection_id)
            
            # Delete document
            delete_doc_query = """
                DELETE FROM langconnect.langchain_pg_document
                WHERE id = $1 AND collection_id = $2
                RETURNING id
            """
            result = await conn.fetchrow(delete_doc_query, document_id, actual_collection_id)
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to delete document"
                )
        
        document_name = (
            metadata.get("title") or 
            metadata.get("original_filename") or 
            metadata.get("source_name") or 
            "Unknown"
        )
        
        logger.info(f"[FS_DELETE_FILE] Deleted document {document_id} and {chunk_count} chunks")
        return DeleteFileResponse(
            success=True,
            document_id=document_id,
            collection_id=actual_collection_id,
            document_name=document_name,
            chunks_deleted=chunk_count,
            message="Document and all associated chunks deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[FS_DELETE_FILE] Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}"
        )

