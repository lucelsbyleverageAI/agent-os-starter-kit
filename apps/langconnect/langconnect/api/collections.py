from typing import Annotated, Any, Optional, Union, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, File, Form, UploadFile
from pydantic import BaseModel

from langconnect.auth import AuthenticatedActor, ServiceAccount, resolve_user_or_service
from langconnect.database.collections import CollectionsManager, CollectionPermissionsManager, Collection
from langconnect.database.notifications import NotificationManager
from langconnect.database.user_roles import UserRoleManager
 
from langconnect.services.job_service import job_service
from langconnect.models import (
    CollectionCreate, 
    CollectionResponse, 
    CollectionUpdate,
    CollectionShareRequest,
    CollectionShareResponse,
    CollectionPermissionResponse,
    PermissionLevel,
)
from langconnect.models.search import SearchQuery, SearchResult, ContextualSearchQuery, KeywordSearchQuery, HybridSearchQuery, FormattedSearchResult, LLMSearchResponse
from langconnect.models.job import (
    JobCreate,
    JobType,
    JobStatus,
    ProcessingOptions,
    JobSubmissionResponse
)

router = APIRouter(prefix="/collections", tags=["collections"])


# =====================
# Admin Collections Endpoint
# =====================

@router.get("/admin/all", response_model=list[CollectionResponse])
async def admin_list_all_collections(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Lists ALL collections in the system. Only accessible to dev_admin users."""
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    try:
        # Create a service account-enabled collections manager to get ALL collections
        collections_manager = CollectionsManager(actor.identity)
        collections_manager._is_service_account = True  # Enable admin access
        
        collections = await collections_manager.list()
        
        
        
        return [CollectionResponse(**c) for c in collections]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list all collections: {str(e)}"
        )


# =====================
# Regular Collections Endpoints
# =====================

@router.post(
    "",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def collections_create(
    collection_data: CollectionCreate,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Creates a new PGVector collection by name with optional metadata and sharing."""
    # Service accounts must specify an owner when creating collections
    if isinstance(actor, ServiceAccount):
        if not collection_data.metadata or not collection_data.metadata.get("owner_id"):
            raise HTTPException(
                status_code=400, 
                detail="Service account must specify 'owner_id' in metadata when creating collections"
            )
        
        # Use the specified owner_id for collection creation
        owner_id = collection_data.metadata["owner_id"]
    else:
        # For regular users, use their identity as owner
        owner_id = actor.identity

    # Create the collection first
    collection_info = await CollectionsManager(owner_id).create(
        collection_data.name, collection_data.metadata
    )
    if not collection_info:
        raise HTTPException(status_code=500, detail="Failed to create collection")
    
    
    
    # If sharing is requested, share with the specified users
    if collection_data.share_with:
        try:
            # Convert share request to format expected by database layer
            users_permissions = [
                {
                    "user_id": user_perm.user_id,
                    "permission_level": user_perm.permission_level.value,
                }
                for user_perm in collection_data.share_with
            ]
            
            # Create collections manager and set service account flag if needed
            collections_manager = CollectionsManager(owner_id)
            if isinstance(actor, ServiceAccount):
                collections_manager._is_service_account = True
            
            # Share the collection
            result = await collections_manager.share_collection(
                collection_info["uuid"], users_permissions
            )
            
            
            
            # Log any sharing errors but don't fail the creation
            if result.get("errors"):
                import logging
                log = logging.getLogger(__name__)
                log.warning(f"Collection {collection_info['uuid']} created but some sharing failed: {result['errors']}")
                
        except Exception as e:
            import logging
            log = logging.getLogger(__name__)
            log.error(f"Collection {collection_info['uuid']} created but sharing failed: {str(e)}")
    
    return CollectionResponse(**collection_info)


@router.get("", response_model=list[CollectionResponse])
async def collections_list(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Lists all available PGVector collections (name and UUID)."""
    # Create collections manager and set service account flag if needed
    collections_manager = CollectionsManager(actor.identity)
    if isinstance(actor, ServiceAccount):
        collections_manager._is_service_account = True
    
    collections = await collections_manager.list()
    
    # Note: List operations are not logged as activities (only CRUD operations are logged)
    
    return [CollectionResponse(**c) for c in collections]


@router.get("/{collection_id}", response_model=CollectionResponse)
async def collections_get(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
):
    """Retrieves details (name and UUID) of a specific PGVector collection."""
    # Create collections manager and set service account flag if needed
    collections_manager = CollectionsManager(actor.identity)
    if isinstance(actor, ServiceAccount):
        collections_manager._is_service_account = True
    
    collection = await collections_manager.get(str(collection_id))
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection '{collection_id}' not found",
        )
    
    # Note: Successful get operations are not logged as activities (only CRUD operations are logged)
    
    return CollectionResponse(**collection)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def collections_delete(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
):
    """Deletes a specific PGVector collection by name."""
    try:
        # Get collection info before deletion for logging
        collection = await CollectionsManager(actor.identity).get(str(collection_id))
        collection_name = collection.get("name") if collection else "unknown"
        
        await CollectionsManager(actor.identity).delete(str(collection_id))
        
        
        
        # No return statement - HTTP 204 must have empty body
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete collection: {str(e)}"
        )


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def collections_update(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    collection_data: CollectionUpdate,
):
    """Updates a specific PGVector collection's name and/or metadata."""
    # Get original collection for comparison
    original_collection = await CollectionsManager(actor.identity).get(str(collection_id))
    
    updated_collection = await CollectionsManager(actor.identity).update(
        str(collection_id),
        name=collection_data.name,
        metadata=collection_data.metadata,
    )

    if not updated_collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to update collection '{collection_id}'",
        )

    # Log successful update with changes
    changes = {}
    if collection_data.name and collection_data.name != original_collection.get("name"):
        changes["name_changed"] = {
            "from": original_collection.get("name"),
            "to": collection_data.name
        }
    if collection_data.metadata:
        changes["metadata_updated"] = collection_data.metadata

    

    return CollectionResponse(**updated_collection)


# =====================
# Collection Sharing Endpoints
# =====================


@router.post("/{collection_id}/share", response_model=CollectionShareResponse)
async def collections_share(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    share_request: CollectionShareRequest,
):
    """Create sharing notifications for a collection with multiple users."""
    try:
        # Get collection info for logging and validation
        collections_manager = CollectionsManager(actor.identity)
        if isinstance(actor, ServiceAccount):
            collections_manager._is_service_account = True
            
        collection = await collections_manager.get(str(collection_id))
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found or access denied")
            
        collection_name = collection.get("name", "unknown")
        
        # Create notifications for each user
        notification_manager = NotificationManager()
        created_notifications = []
        errors = []
        
        for user_perm in share_request.users:
            try:
                # Create notification with collection metadata
                notification_id = await notification_manager.create_notification(
                    recipient_user_id=user_perm.user_id,
                    notification_type="collection_share",
                    resource_id=str(collection_id),
                    resource_type="collection",
                    permission_level=user_perm.permission_level.value,
                    sender_user_id=actor.identity,
                    sender_display_name=actor.identity,  # TODO: Get actual display name
                    resource_name=collection_name,
                    resource_description=collection.get("metadata", {}).get("description")
                )
                
                created_notifications.append({
                    "notification_id": notification_id,
                    "user_id": user_perm.user_id,
                    "permission_level": user_perm.permission_level.value,
                    "collection_name": collection_name
                })
                
            except Exception as e:
                errors.append(f"Failed to share with user {user_perm.user_id}: {str(e)}")
        
        
        
        # Return successful response - permissions will be created when notifications are accepted
        # For now, return empty shared_permissions since no direct permissions were granted
        return CollectionShareResponse(
            success=len(errors) == 0,
            shared_with=[],  # No immediate permissions granted - they'll be created when notifications are accepted
            errors=errors
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create sharing notifications: {str(e)}",
        )


@router.get("/{collection_id}/permissions", response_model=list[CollectionPermissionResponse])
async def collections_get_permissions(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
):
    """List all permissions for a collection."""
    try:
        permissions_manager = CollectionPermissionsManager(actor.identity)
        if isinstance(actor, ServiceAccount):
            permissions_manager._is_service_account = True
            
        permissions = await permissions_manager.list_collection_permissions(
            str(collection_id)
        )
        
        return [
            CollectionPermissionResponse(
                id=perm["id"],
                collection_id=perm["collection_id"],
                user_id=perm["user_id"],
                permission_level=PermissionLevel(perm["permission_level"]),
                granted_by=perm["granted_by"],
                created_at=perm["created_at"],
                updated_at=perm["updated_at"],
            )
            for perm in permissions
        ]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get collection permissions: {str(e)}",
        )


@router.delete("/{collection_id}/permissions/{user_id}", status_code=status.HTTP_200_OK)
async def collections_revoke_permission(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    user_id: str,
):
    """Revoke a user's permission to access a collection."""
    try:
        # Get collection info for logging
        collection = await CollectionsManager(actor.identity).get(str(collection_id))
        collection_name = collection.get("name") if collection else "unknown"
        
        permissions_manager = CollectionPermissionsManager(actor.identity)
        if isinstance(actor, ServiceAccount):
            permissions_manager._is_service_account = True
            
        await permissions_manager.revoke_permission(
            str(collection_id), user_id
        )
        
        
        
        return {"message": "Permission revoked successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke permission: {str(e)}",
        )


# =====================
# Collection Stats Endpoint
# =====================

class CollectionStatsResponse(BaseModel):
    """Collection statistics response."""
    collection_id: str
    uses_document_model: bool
    document_stats: Optional[dict[str, Any]] = None
    legacy_chunk_stats: Optional[dict[str, Any]] = None


@router.get(
    "/{collection_id}/stats",
    response_model=CollectionStatsResponse
)
async def get_collection_stats(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
):
    """Get statistics about documents and chunks in a collection."""
    
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
    
    # Check if collection uses new document model
    uses_document_model = await collection.has_document_model()
    
    response = CollectionStatsResponse(
        collection_id=str(collection_id),
        uses_document_model=uses_document_model
    )
    
    if uses_document_model:
        # Get document model statistics
        response.document_stats = await collection.get_document_stats()
    else:
        # Get legacy chunk statistics
        legacy_docs = await collection.list(limit=1000)  # Get many for stats
        
        source_types = {}
        total_content_length = 0
        for doc in legacy_docs:
            metadata = doc.get("metadata", {})
            source_type = metadata.get("source_type", "unknown")
            source_types[source_type] = source_types.get(source_type, 0) + 1
            total_content_length += len(doc.get("content", ""))
        
        response.legacy_chunk_stats = {
            "chunk_count": len(legacy_docs),
            "total_content_length": total_content_length,
            "avg_content_length": total_content_length // len(legacy_docs) if legacy_docs else 0,
            "source_breakdown": source_types
        }
    
    return response


# =====================
# Collection Search Endpoint
# =====================

@router.post(
    "/{collection_id}/semantic_search",
    response_model=Union[List[SearchResult], LLMSearchResponse],
)
async def semantic_search_collection(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    query: ContextualSearchQuery,
):
    """Search for content within a collection using semantic vector similarity.
    
    Enhanced search with optional contextual expansion and LLM formatting.
    Searches across all chunks/embeddings in the collection and returns results
    ranked by semantic similarity to the query.
    
    Returns:
        - List[SearchResult] when format_chunks_for_llm=false (default)
        - LLMSearchResponse when format_chunks_for_llm=true (includes both formatted text and structured data)
    """
    
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

    # Create collection instance
    collection = Collection(str(collection_id), effective_user_id)
    
    # For service accounts, set the service account flag
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True
    
    try:
        # Perform contextual search
        results = await collection.contextual_search(
            query=query.query,
            limit=query.limit,
            filter=query.filter,
            return_surrounding_context=query.return_surrounding_context,
            max_context_characters=query.max_context_characters,
            format_chunks_for_llm=query.format_chunks_for_llm,
        )
        
        
        
        return results
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.post(
    "/{collection_id}/keyword_search",
    response_model=Union[List[SearchResult], LLMSearchResponse],
)
async def keyword_search_collection(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    query: KeywordSearchQuery,
):
    """Search for content within a collection using keyword-based full-text search.
    
    Enhanced keyword search with optional contextual expansion and LLM formatting.
    Searches across all chunks/embeddings in the collection using PostgreSQL's 
    full-text search capabilities and returns results ranked by keyword relevance.
    
    Returns:
        - List[SearchResult] when format_chunks_for_llm=false (default)
        - LLMSearchResponse when format_chunks_for_llm=true (includes both formatted text and structured data)
    """
    
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

    # Create collection instance
    collection = Collection(str(collection_id), effective_user_id)
    
    # For service accounts, set the service account flag
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True
    
    try:
        # Perform keyword search
        results = await collection.keyword_search(
            keywords=query.keywords,
            limit=query.limit,
            filter=query.filter,
            return_surrounding_context=query.return_surrounding_context,
            max_context_characters=query.max_context_characters,
            format_chunks_for_llm=query.format_chunks_for_llm,
        )
        
        
        
        return results
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Keyword search failed: {str(e)}"
        )


@router.post(
    "/{collection_id}/hybrid_search",
    response_model=Union[List[SearchResult], LLMSearchResponse],
)
async def hybrid_search_collection(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    collection_id: UUID,
    query: HybridSearchQuery,
):
    """Search for content within a collection using hybrid semantic and keyword search.
    
    Enhanced hybrid search combining semantic vector similarity with keyword-based 
    full-text search. Includes optional contextual expansion and LLM formatting.
    Results are ranked using a weighted combination of both search methods.
    
    Returns:
        - List[SearchResult] when format_chunks_for_llm=false (default)
        - LLMSearchResponse when format_chunks_for_llm=true (includes both formatted text and structured data)
    """
    
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

    # Create collection instance
    collection = Collection(str(collection_id), effective_user_id)
    
    # For service accounts, set the service account flag
    if isinstance(actor, ServiceAccount):
        collection._is_service_account = True
        collection.permissions_manager._is_service_account = True
    
    try:
        # Perform hybrid search
        results = await collection.hybrid_search(
            query=query.query,
            keywords=query.keywords,
            limit=query.limit,
            filter=query.filter,
            return_surrounding_context=query.return_surrounding_context,
            max_context_characters=query.max_context_characters,
            format_chunks_for_llm=query.format_chunks_for_llm,
            semantic_weight=query.semantic_weight,
        )
        
        
        
        return results
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Hybrid search failed: {str(e)}"
        )





# =====================
# Enhanced Document Processing Endpoints (MOVED TO DOCUMENTS ROUTER)
# =====================
# These endpoints have been moved to the documents router for better organization


# MOVED TO /collections/{collection_id}/documents in documents router


# MOVED TO /collections/{collection_id}/documents/batch in documents router
