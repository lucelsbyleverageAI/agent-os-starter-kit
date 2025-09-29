"""Chunk API endpoints for chunk-level operations (embeddings/vector search)."""

import logging
from typing import Annotated, Any, Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from langconnect.auth import AuthenticatedActor, ServiceAccount, resolve_user_or_service
from langconnect.database.collections import Collection, CollectionsManager
 

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chunks"])


# Response Models
class ChunkSummary(BaseModel):
    """Summary information for a chunk (embedding)."""
    id: str
    content_preview: str  # First 200 chars
    content_length: int
    document_id: Optional[str] = None  # Link to parent document if using new model
    metadata: dict[str, Any]
    similarity_score: Optional[float] = None  # For search results


class ChunkDetail(BaseModel):
    """Detailed chunk information including full content."""
    id: str
    content: str
    document_id: Optional[str] = None
    metadata: dict[str, Any]
    embedding: Optional[List[float]] = None  # Only included if explicitly requested


class ChunkListResponse(BaseModel):
    """Response for chunk listing."""
    chunks: List[ChunkSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


@router.get(
    "/collections/{collection_id}/chunks",
    response_model=ChunkListResponse
)
async def list_chunks(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    document_id: Optional[str] = Query(None, description="Filter chunks by document ID"),
):
    """List chunks (embeddings) in a collection."""
    
    # Resolve effective user ID for service accounts
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity

    collection = Collection(str(collection_id), effective_user_id)
    
    # For service accounts, set the service account flag on the collection and permission manager
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True
    
    # Get chunks from the embeddings table
    chunks_data = await collection.list(limit=limit, offset=offset)
    
    # Filter by document_id if specified
    if document_id:
        chunks_data = [
            chunk for chunk in chunks_data 
            if chunk.get("metadata", {}).get("document_id") == document_id
        ]
    
    chunks = []
    for chunk_data in chunks_data:
        content = chunk_data.get("content", "")
        metadata = chunk_data.get("metadata", {})
        
        # Get chunk ID with fallback from metadata if available
        chunk_id = chunk_data.get("id") or metadata.get("id")
        if not chunk_id:
            chunk_id = f"missing-{hash(content[:100]) % 100000}"
        
        # Get document_id from metadata or chunk_data
        document_id = metadata.get("document_id") or chunk_data.get("document_id")
        
        chunks.append(ChunkSummary(
            id=chunk_id,
            content_preview=content[:200] + "..." if len(content) > 200 else content,
            content_length=len(content),
            document_id=document_id,
            metadata=metadata
        ))
    
    # For total count, we approximate (could be made more accurate with a separate query)
    total = len(chunks_data)
    
    return ChunkListResponse(
        chunks=chunks,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(chunks) < total
    )


@router.get(
    "/collections/{collection_id}/chunks/{chunk_id}",
    response_model=ChunkDetail
)
async def get_chunk_detail(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    chunk_id: str,
    include_embedding: bool = Query(False, description="Include the embedding vector in response"),
):
    """Get full chunk details including content."""
    
    # Resolve effective user ID for service accounts
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity

    collection = Collection(str(collection_id), effective_user_id)
    
    # For service accounts, set the service account flag on the collection and permission manager
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True
    
    # Get specific chunk
    chunk_data = await collection.get(chunk_id)
    
    if not chunk_data:
        raise HTTPException(status_code=404, detail="Chunk not found")
    
    metadata = chunk_data.get("metadata", {})
    
    # Get chunk ID with fallback from metadata if available
    chunk_id = chunk_data.get("id") or metadata.get("id")
    if not chunk_id:
        chunk_id = f"missing-{hash(chunk_data.get('content', '')[:100]) % 100000}"
    
    # Get document_id from metadata or chunk_data
    document_id = metadata.get("document_id") or chunk_data.get("document_id")
    
    return ChunkDetail(
        id=chunk_id,
        content=chunk_data.get("content", ""),
        document_id=document_id,
        metadata=metadata,
        embedding=chunk_data.get("embedding") if include_embedding else None
    )


@router.delete(
    "/collections/{collection_id}/chunks/{chunk_id}",
    response_model=dict[str, bool]
)
async def delete_chunk(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    chunk_id: str,
):
    """Delete a specific chunk/embedding."""
    
    # Resolve effective user ID for service accounts
    if isinstance(actor, ServiceAccount):
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True
        collection_details = await collections_manager.get(str(collection_id))
        if not collection_details:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
        effective_user_id = collection_details["metadata"].get("owner_id")
        if not effective_user_id:
            raise HTTPException(status_code=400, detail="Collection missing owner_id in metadata")
    else:
        effective_user_id = actor.identity

    collection = Collection(str(collection_id), effective_user_id)
    
    # For service accounts, set the service account flag
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True
    
    try:
        # First, get the chunk to find its file_id for deletion
        chunk_data = await collection.get(chunk_id)
        if not chunk_data:
            raise HTTPException(status_code=404, detail="Chunk not found")
        
        # Get file_id from metadata for deletion
        file_id = chunk_data.get("metadata", {}).get("file_id")
        if not file_id:
            # If no file_id, we need to delete by direct database query
            # This is a limitation of the current Collection.delete() method
            from langconnect.database.connection import get_db_connection
            async with get_db_connection() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM langconnect.langchain_pg_embedding 
                    WHERE id = $1 AND collection_id = $2
                    """,
                    chunk_id,
                    collection.collection_id
                )
                deleted_count = int(result.split()[-1])
                success = deleted_count > 0
        else:
            # Use the existing delete method with file_id
            success = await collection.delete(file_id=file_id)
        
        if success:
            pass
        return {"success": success}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete chunk: {str(e)}"
        )


 