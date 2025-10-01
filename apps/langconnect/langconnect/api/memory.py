"""
Memory API endpoints for Mem0 integration.

This module provides REST API endpoints for managing AI agent memories using the mem0 library.
All operations are secured and isolated by user authentication.
"""

import logging
from typing import Annotated, Optional, Union, List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from langconnect.auth import AuthenticatedActor, ServiceAccount, resolve_user_or_service
from langconnect.services.memory_service import memory_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@router.get("/health")
async def memory_health_check():
    """
    Health check endpoint for the memory service.
    Returns the status of the memory service initialization.
    """
    try:
        is_available = hasattr(memory_service, '_memory_client') and memory_service._memory_client is not None
        
        if is_available:
            return {
                "status": "healthy",
                "message": "Memory service is initialized and ready",
                "service_available": True
            }
        else:
            return {
                "status": "unhealthy", 
                "message": "Memory service failed to initialize. Check server logs for details.",
                "service_available": False
            }
    except Exception as e:
        logger.error(f"Memory health check failed: {e}")
        return {
            "status": "error",
            "message": f"Memory health check failed: {str(e)}",
            "service_available": False
        }


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class MemoryAddRequest(BaseModel):
    """Request model for adding a new memory."""
    content: Union[str, List[Dict[str, str]]] = Field(
        ..., 
        description="Memory content - either a string or list of message dicts"
    )
    user_id: Optional[str] = Field(
        None,
        description="User ID (required when using service account authentication)"
    )
    agent_id: Optional[str] = Field(
        None, 
        description="Optional agent/assistant ID this memory relates to"
    )
    run_id: Optional[str] = Field(
        None, 
        description="Optional conversation/run ID this memory is from"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, 
        description="Optional additional metadata for the memory"
    )


class MemorySearchRequest(BaseModel):
    """Request model for searching memories."""
    query: str = Field(..., description="Search query for finding relevant memories")
    user_id: Optional[str] = Field(
        None,
        description="User ID (required when using service account authentication)"
    )
    agent_id: Optional[str] = Field(
        None, 
        description="Optional agent ID to filter results"
    )
    run_id: Optional[str] = Field(
        None, 
        description="Optional run ID to filter results"
    )
    filters: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional structured filters (JSON format) for metadata, content, topic, type, etc. Supports AND/OR logic and nested conditions"
    )
    limit: int = Field(5, ge=1, le=100, description="Maximum number of results to return")
    threshold: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0, 
        description="Minimum similarity threshold (0.0-1.0)"
    )


class MemoryGetAllRequest(BaseModel):
    """Request model for getting all memories."""
    user_id: Optional[str] = Field(
        None,
        description="User ID (required when using service account authentication)"
    )
    agent_id: Optional[str] = Field(
        None, 
        description="Optional agent ID to filter results"
    )
    run_id: Optional[str] = Field(
        None, 
        description="Optional run ID to filter results"
    )
    filters: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional structured filters (JSON format) for metadata, content, topic, type, etc. Supports AND/OR logic and nested conditions"
    )
    limit: int = Field(100, ge=1, le=1000, description="Maximum number of memories to return")


class MemoryUpdateRequest(BaseModel):
    """Request model for updating a memory."""
    content: Optional[str] = Field(None, description="New content for the memory")
    metadata: Optional[Dict[str, Any]] = Field(
        None, 
        description="New metadata for the memory"
    )


class MemoryDeleteAllRequest(BaseModel):
    """Request model for deleting all memories with optional filtering."""
    user_id: Optional[str] = Field(
        None,
        description="User ID (required when using service account authentication)"
    )
    agent_id: Optional[str] = Field(
        None, 
        description="Optional agent ID to filter deletions"
    )
    run_id: Optional[str] = Field(
        None, 
        description="Optional run ID to filter deletions"
    )
    filters: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional structured filters (JSON format) for metadata, content, topic, type, etc. Supports AND/OR logic and nested conditions"
    )


class MemoryResponse(BaseModel):
    """Generic response model for memory operations."""
    success: bool = Field(..., description="Whether the operation was successful")
    data: Optional[Dict[str, Any]] = Field(None, description="Operation result data")
    message: Optional[str] = Field(None, description="Optional message")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_user_id_from_actor(actor: AuthenticatedActor, request_user_id: Optional[str] = None) -> str:
    """Extract user ID from authenticated actor.
    
    Args:
        actor: The authenticated actor (User or ServiceAccount)
        request_user_id: Optional user_id from request body (for service account impersonation)
        
    Returns:
        str: The user ID to use for the operation
        
    Raises:
        HTTPException: If service account tries to operate without specifying a user_id
    """
    if isinstance(actor, ServiceAccount):
        # Service accounts must specify which user they're acting on behalf of
        if not request_user_id:
            raise HTTPException(
                status_code=400,
                detail="user_id is required in request body when using service account authentication"
            )
        logger.info(f"Service account acting on behalf of user: {request_user_id}")
        return request_user_id
    else:
        # Regular users - use their authenticated identity, ignore any request_user_id
        return actor.identity


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/add", response_model=MemoryResponse)
async def add_memory(
    request: MemoryAddRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """
    Add a new memory for the authenticated user.
    
    This endpoint allows users to store new memories that can be retrieved later
    by agents during conversations. Memories can be associated with specific
    agents or conversation runs for better organization.
    """
    try:
        user_id = get_user_id_from_actor(actor, request.user_id)
        
        result = await memory_service.add_memory(
            user_id=user_id,
            content=request.content,
            agent_id=request.agent_id,
            run_id=request.run_id,
            metadata=request.metadata
        )
        
        logger.info(f"Added memory for user {user_id}")
        return MemoryResponse(
            success=True,
            data=result,
            message="Memory added successfully"
        )
        
    except ValueError as e:
        logger.warning(f"Invalid memory add request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to add memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add memory"
        )


@router.post("/search", response_model=MemoryResponse)
async def search_memories(
    request: MemorySearchRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """
    Search for memories using semantic similarity.
    
    This endpoint allows users and agents to find relevant memories based on
    a natural language query. Results are ranked by semantic similarity and
    can be filtered by agent or run context.
    """
    try:
        user_id = get_user_id_from_actor(actor, request.user_id)
        
        results = await memory_service.search_memories(
            user_id=user_id,
            query=request.query,
            agent_id=request.agent_id,
            run_id=request.run_id,
            filters=request.filters,
            limit=request.limit,
            threshold=request.threshold
        )
        
        logger.info(f"Searched memories for user {user_id}, found {len(results.get('results', []))} results")
        return MemoryResponse(
            success=True,
            data=results,
            message="Memory search completed successfully"
        )
        
    except ValueError as e:
        logger.warning(f"Invalid memory search request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search memories"
        )


@router.get("/all", response_model=MemoryResponse)
async def get_all_memories(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    Get all memories for the authenticated user with optional filtering (GET version).
    
    This endpoint retrieves all memories belonging to the user, with optional
    filtering by agent or run context. For complex filtering, use the POST version.
    
    Note: user_id parameter is required when using service account authentication.
    """
    try:
        resolved_user_id = get_user_id_from_actor(actor, user_id)
        
        # Check if memory service is available
        if not hasattr(memory_service, '_memory_client') or memory_service._memory_client is None:
            logger.error("Memory service is not initialized")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service is not available. Please check server configuration and logs."
            )
        
        # Adjust limit to account for offset
        actual_limit = limit + offset
        
        results = await memory_service.get_all_memories(
            user_id=resolved_user_id,
            agent_id=agent_id,
            run_id=run_id,
            filters=None,  # No complex filtering in GET version
            limit=actual_limit
        )
        
        # Apply offset manually since mem0 doesn't support it directly
        all_results = results.get('results', [])
        paginated_results = all_results[offset:offset + limit]
        
        # Update results with paginated data
        paginated_response = results.copy()
        paginated_response['results'] = paginated_results
        paginated_response['total'] = len(all_results)
        paginated_response['offset'] = offset
        paginated_response['limit'] = limit
        
        logger.info(f"Retrieved {len(paginated_results)} memories for user {resolved_user_id} (offset: {offset}, limit: {limit})")
        return MemoryResponse(
            success=True,
            data=paginated_response,
            message=f"Retrieved {len(paginated_results)} memories"
        )
        
    except ValueError as e:
        logger.warning(f"Invalid get all memories request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get all memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve memories"
        )


@router.post("/all", response_model=MemoryResponse)
async def get_all_memories_with_filters(
    request: MemoryGetAllRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """
    Get all memories for the authenticated user with advanced filtering (POST version).
    
    This endpoint supports complex JSON-based filtering for metadata, content, topic, 
    type, and other custom fields using AND/OR logic and nested conditions.
    """
    try:
        user_id = get_user_id_from_actor(actor, request.user_id)
        
        # Check if memory service is available
        if not hasattr(memory_service, '_memory_client') or memory_service._memory_client is None:
            logger.error("Memory service is not initialized")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service is not available. Please check server configuration and logs."
            )
        
        results = await memory_service.get_all_memories(
            user_id=user_id,
            agent_id=request.agent_id,
            run_id=request.run_id,
            filters=request.filters,
            limit=request.limit
        )
        
        logger.info(f"Retrieved {len(results.get('results', []))} memories for user {user_id} with advanced filters")
        return MemoryResponse(
            success=True,
            data=results,
            message="All memories retrieved successfully"
        )
        
    except ValueError as e:
        logger.warning(f"Invalid get all memories request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get all memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve memories"
        )


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    user_id: Optional[str] = None
):
    """
    Get a specific memory by its ID.
    
    This endpoint retrieves a single memory by its unique identifier.
    Users can only access their own memories.
    
    Note: user_id parameter is required when using service account authentication.
    """
    try:
        resolved_user_id = get_user_id_from_actor(actor, user_id)
        
        memory = await memory_service.get_memory(
            user_id=resolved_user_id,
            memory_id=memory_id
        )
        
        logger.info(f"Retrieved memory {memory_id} for user {resolved_user_id}")
        return MemoryResponse(
            success=True,
            data=memory,
            message="Memory retrieved successfully"
        )
        
    except ValueError as e:
        logger.warning(f"Invalid get memory request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        if "does not belong to user" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve memory"
        )
    except Exception as e:
        logger.error(f"Failed to get memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve memory"
        )




@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    user_id: Optional[str] = None
):
    """
    Update an existing memory.
    
    This endpoint allows users to modify the content or metadata of an existing
    memory. Users can only update their own memories.
    
    Note: user_id parameter is required when using service account authentication.
    """
    try:
        resolved_user_id = get_user_id_from_actor(actor, user_id)
        
        result = await memory_service.update_memory(
            user_id=resolved_user_id,
            memory_id=memory_id,
            content=request.content,
            metadata=request.metadata
        )
        
        logger.info(f"Updated memory {memory_id} for user {resolved_user_id}")
        return MemoryResponse(
            success=True,
            data=result,
            message="Memory updated successfully"
        )
        
    except ValueError as e:
        logger.warning(f"Invalid update memory request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update memory"
        )
    except Exception as e:
        logger.error(f"Failed to update memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update memory"
        )


@router.delete("/{memory_id}", response_model=MemoryResponse)
async def delete_memory(
    memory_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    user_id: Optional[str] = None
):
    """
    Delete a specific memory by its ID.
    
    This endpoint permanently deletes a memory. Users can only delete their
    own memories. This operation cannot be undone.
    
    Note: user_id parameter is required when using service account authentication.
    """
    try:
        resolved_user_id = get_user_id_from_actor(actor, user_id)
        
        result = await memory_service.delete_memory(
            user_id=resolved_user_id,
            memory_id=memory_id
        )
        
        logger.info(f"Deleted memory {memory_id} for user {resolved_user_id}")
        return MemoryResponse(
            success=True,
            data=result,
            message="Memory deleted successfully"
        )
        
    except ValueError as e:
        logger.warning(f"Invalid delete memory request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete memory"
        )
    except Exception as e:
        logger.error(f"Failed to delete memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete memory"
        )


@router.post("/delete-all", response_model=MemoryResponse)
async def delete_all_memories(
    request: MemoryDeleteAllRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
):
    """
    Delete all memories for the authenticated user with optional filtering.
    
    This endpoint permanently deletes multiple memories at once. Can be filtered
    by agent or run context. This operation cannot be undone.
    """
    try:
        user_id = get_user_id_from_actor(actor, request.user_id)
        
        result = await memory_service.delete_all_memories(
            user_id=user_id,
            agent_id=request.agent_id,
            run_id=request.run_id
        )
        
        logger.info(f"Deleted all memories for user {user_id} (agent: {request.agent_id}, run: {request.run_id})")
        return MemoryResponse(
            success=True,
            data=result,
            message="All matching memories deleted successfully"
        )
        
    except ValueError as e:
        logger.warning(f"Invalid delete all memories request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to delete all memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete memories"
        )


@router.get("/{memory_id}/history", response_model=MemoryResponse)
async def get_memory_history(
    memory_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    user_id: Optional[str] = None
):
    """
    Get the change history for a specific memory.
    
    This endpoint retrieves the history of changes made to a memory over time.
    Useful for understanding how memories have evolved and for debugging.
    
    Note: user_id parameter is required when using service account authentication.
    """
    try:
        resolved_user_id = get_user_id_from_actor(actor, user_id)
        
        history = await memory_service.get_memory_history(
            user_id=resolved_user_id,
            memory_id=memory_id
        )
        
        logger.info(f"Retrieved history for memory {memory_id} for user {resolved_user_id}")
        return MemoryResponse(
            success=True,
            data={"history": history},
            message="Memory history retrieved successfully"
        )
        
    except ValueError as e:
        logger.warning(f"Invalid get memory history request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve memory history"
        )
    except Exception as e:
        logger.error(f"Failed to get memory history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve memory history"
        )


# Export the router for registration in the main application
memory_router = router
