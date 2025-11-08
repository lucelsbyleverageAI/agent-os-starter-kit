"""
Assistant lifecycle management endpoints: listing, registration, details, updates, deletion, and sync.
"""

import json
import logging
import time
from typing import Annotated, Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.models.agent import (
    AssistantInfo,
    AssistantListResponse,
    AssistantDetailsResponse,
    AssistantRegistrationRequest,
    AssistantUpdateRequest,
    AssistantUpdateResponse,
    AssistantDeleteResponse,
    AssistantPermissionInfo,
)
from langconnect.services.langgraph_integration import get_langgraph_service, LangGraphService

from langconnect.services.langgraph_sync import LangGraphSyncService, get_sync_service
from langconnect.services.permission_service import PermissionService
from langconnect.database.permissions import GraphPermissionsManager, AssistantPermissionsManager
from langconnect.database.connection import get_db_connection
from uuid import UUID

# Set up logging
log = logging.getLogger(__name__)

# Create router
router = APIRouter()


@router.get("/assistants", response_model=AssistantListResponse)
async def list_accessible_assistants(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> AssistantListResponse:
    """
    List assistants accessible to the current user.
    
    Returns only assistants that the user has permissions to access,
    including both owned assistants and those shared with them.
    
    **Authorization:**
    - **All Users**: Can list their accessible assistants
    - **Service Accounts**: Can see all assistants (but must specify owner_id for operations)
    """
    try:
        log.info(f"Listing accessible assistants for {actor.actor_type}:{actor.identity}")
        
        if actor.actor_type == "service":
            # Service accounts can see all assistants from LangGraph
            assistants_data = await langgraph_service._make_request(
                "POST", 
                "assistants/search", 
                data={"limit": 1000, "offset": 0}
            )
            langgraph_assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
            
            # Convert to AssistantInfo format (no permission filtering for service accounts)
            assistants = []
            for assistant in langgraph_assistants:
                # Get metadata if it exists in our system
                metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant.get("assistant_id"))

                # Get allowed actions for service account (always has admin access)
                allowed_actions = ["view", "chat", "edit", "delete", "share", "manage_access"]

                assistant_info = AssistantInfo(
                    assistant_id=assistant.get("assistant_id"),
                    graph_id=assistant.get("graph_id"),
                    name=assistant.get("name", "Unknown"),
                    description=metadata.get("description") if metadata else None,
                    permission_level="admin",  # Service accounts have admin access
                    owner_id=metadata.get("owner_id") if metadata else "unknown",
                    owner_display_name=metadata.get("owner_display_name") if metadata else None,
                    created_at=assistant.get("created_at", ""),
                    updated_at=assistant.get("updated_at"),
                    metadata=assistant.get("metadata"),
                    allowed_actions=allowed_actions
                )
                assistants.append(assistant_info)
            
            total_count = len(assistants)
            owned_count = 0  # Service accounts don't "own" assistants
            shared_count = total_count
            
        else:
            # Regular users - get permission-filtered assistants
            user_assistants = await AssistantPermissionsManager.get_user_accessible_assistants(actor.identity)
            
            assistants = []
            owned_count = 0
            shared_count = 0
            
            for assistant_data in user_assistants:
                # Get LangGraph data for this assistant
                try:
                    langgraph_assistant = await langgraph_service._make_request(
                        "GET",
                        f"assistants/{assistant_data['assistant_id']}"
                    )
                except Exception as e:
                    log.warning(f"Could not get LangGraph data for assistant {assistant_data['assistant_id']}: {e}")
                    langgraph_assistant = {}

                # Get allowed actions for this user (Phase 3: Centralized permissions)
                allowed_actions = await PermissionService.get_allowed_actions(
                    user_id=actor.identity,
                    resource_type="assistant",
                    resource_id=assistant_data["assistant_id"],
                    resource_metadata=langgraph_assistant
                )

                assistant_info = AssistantInfo(
                    assistant_id=assistant_data["assistant_id"],
                    graph_id=assistant_data["graph_id"],
                    name=langgraph_assistant.get("name", assistant_data["display_name"] or "Unknown"),
                    description=assistant_data["description"],
                    permission_level=assistant_data["permission_level"],
                    owner_id=assistant_data["owner_id"],
                    owner_display_name=assistant_data["owner_display_name"],
                    created_at=assistant_data["assistant_created_at"].isoformat() if assistant_data["assistant_created_at"] else "",
                    updated_at=assistant_data["assistant_updated_at"].isoformat() if assistant_data["assistant_updated_at"] else None,
                    metadata=langgraph_assistant.get("metadata"),
                    allowed_actions=allowed_actions
                )
                assistants.append(assistant_info)
                
                if assistant_data["permission_level"] == "owner":
                    owned_count += 1
                else:
                    shared_count += 1
            
            total_count = len(assistants)
        
        log.info(f"Listed {total_count} accessible assistants for {actor.actor_type}:{actor.identity} ({owned_count} owned, {shared_count} shared)")
        
        return AssistantListResponse(
            assistants=assistants,
            total_count=total_count,
            owned_count=owned_count,
            shared_count=shared_count
        )
        
    except Exception as e:
        log.error(f"Failed to list accessible assistants: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list accessible assistants: {str(e)}"
        )


@router.post("/assistants", response_model=AssistantDetailsResponse)
async def register_assistant(
    request: AssistantRegistrationRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
) -> AssistantDetailsResponse:
    """
    Register an assistant after it's been created in LangGraph.
    
    This endpoint provides the critical link between LangGraph assistant creation
    and our permission system. It should be called immediately after creating
    an assistant in LangGraph to ensure proper tracking and permissions.
    
    **Workflow:**
    1. Frontend creates assistant in LangGraph directly
    2. Frontend calls this endpoint to register it in our permission system
    3. Assistant becomes available through our permission-aware endpoints
    
    **Authorization:**
    - **Users**: Can register assistants they create for graphs they have access to
    - **Service Accounts**: Can register any assistant (must specify owner_id)
    """
    try:
        log.info(f"Registering assistant {request.assistant_id} by {actor.actor_type}:{actor.identity}")
        
        # Step 1: Verify assistant exists in LangGraph
        try:
            langgraph_assistant = await langgraph_service._make_request(
                "GET",
                f"assistants/{request.assistant_id}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=404,
                detail=f"Assistant not found in LangGraph: {str(e)}"
            )
        
        # Step 2: Determine owner and validate permissions
        if actor.actor_type == "service":
            # Service accounts must specify owner
            if not request.owner_id:
                raise HTTPException(
                    status_code=400,
                    detail="Service accounts must specify owner_id when registering assistants"
                )
            owner_id = request.owner_id
            
            # Verify the specified owner exists and can create assistants for this graph
            owner_info = await GraphPermissionsManager.get_user_by_id(owner_id)
            if not owner_info:
                raise HTTPException(
                    status_code=400,
                    detail=f"Specified owner {owner_id} not found"
                )
        else:
            # Regular users become the owner
            owner_id = actor.identity
            
            # Check if user has graph access
            graph_id = langgraph_assistant.get("graph_id")
            if not graph_id:
                raise HTTPException(
                    status_code=400,
                    detail="Assistant must belong to a valid graph"
                )
            
            has_access = await GraphPermissionsManager.has_graph_permission(
                actor.identity, graph_id, "access"
            )
            if not has_access:
                raise HTTPException(
                    status_code=403,
                    detail=f"You do not have access to graph {graph_id}"
                )
        # Pre-step: Ensure assistant exists in mirror before adding FK-constrained permissions
        #
        # This sync is REQUIRED due to foreign key constraint in the database:
        #   assistant_permissions.assistant_id -> assistants_mirror.assistant_id (FK constraint)
        #
        # Without this pre-sync, the permission registration below (Step 3) would fail with:
        #   "violates foreign key constraint fk_assistant_permissions_assistant"
        #
        # The sync fetches the assistant from LangGraph and inserts it into assistants_mirror,
        # allowing the permission system to reference it. This is an architectural requirement,
        # not a performance optimization.
        try:
            sync_service = get_sync_service()
            user_token = getattr(actor, "access_token", None)
            await sync_service.sync_assistant(request.assistant_id, user_token=user_token)
            log.info(f"Pre-synced assistant {request.assistant_id} to mirror before permission registration")
        except Exception as pre_sync_err:
            log.warning(f"Pre-sync failed for assistant {request.assistant_id} (continuing to register permission): {pre_sync_err}")

        # Step 3: Ensure owner permission exists (metadata removed)
        success = await AssistantPermissionsManager.register_assistant(
            assistant_id=request.assistant_id,
            graph_id=langgraph_assistant.get("graph_id"),
            owner_id=owner_id,
            display_name=request.name or langgraph_assistant.get("name"),
            description=request.description
        )
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to register assistant owner permission"
            )
        action = "assistant_registered"
        
        # Step 4: Share with additional users if specified
        sharing_results = []
        if request.share_with:
            for user_share in request.share_with:
                try:
                    # Verify user exists and has graph access
                    user_info = await GraphPermissionsManager.get_user_by_id(user_share["user_id"])
                    if not user_info:
                        sharing_results.append({
                            "user_id": user_share["user_id"],
                            "success": False,
                            "error": "User not found"
                        })
                        continue
                    
                    # Check graph access
                    has_graph_access = await GraphPermissionsManager.has_graph_permission(
                        user_share["user_id"], langgraph_assistant.get("graph_id"), "access"
                    )
                    if not has_graph_access:
                        sharing_results.append({
                            "user_id": user_share["user_id"],
                            "success": False,
                            "error": "User does not have access to the graph"
                        })
                        continue
                    
                    # Grant assistant permission
                    success = await AssistantPermissionsManager.grant_assistant_permission(
                        assistant_id=request.assistant_id,
                        user_id=user_share["user_id"],
                        permission_level="user",
                        granted_by='system:public'
                    )
                    
                    sharing_results.append({
                        "user_id": user_share["user_id"],
                        "success": success,
                        "error": None if success else "Failed to grant permission"
                    })
                    
                except Exception as e:
                    sharing_results.append({
                        "user_id": user_share.get("user_id", "unknown"),
                        "success": False,
                        "error": str(e)
                    })
        
        # Step 5: Get updated assistant metadata
        metadata = await AssistantPermissionsManager.get_assistant_metadata(request.assistant_id)
        
        # Step 6: Get assistant permissions (for owner)
        permissions = []
        if owner_id == actor.identity or actor.actor_type == "service":
            permissions_data = await AssistantPermissionsManager.get_assistant_permissions(request.assistant_id)
            permissions = [
                AssistantPermissionInfo(
                    user_id=perm["user_id"],
                    email=perm["email"] or "Unknown",
                    display_name=perm["display_name"] or "Unknown User",
                    permission_level=perm["permission_level"],
                    granted_by=perm["granted_by"],
                    granted_at=perm["created_at"].isoformat() if perm["created_at"] else "Unknown"
                )
                for perm in permissions_data
            ]

        # Step 6.5: Get allowed actions (Phase 3: Centralized permissions)
        if actor.actor_type == "service":
            allowed_actions = ["view", "chat", "edit", "delete", "share", "manage_access"]
        else:
            allowed_actions = await PermissionService.get_allowed_actions(
                user_id=actor.identity,
                resource_type="assistant",
                resource_id=request.assistant_id,
                resource_metadata=langgraph_assistant
            )

        successful_shares = len([r for r in sharing_results if r["success"]])
        log.info(f"Assistant {request.assistant_id} registered successfully, shared with {successful_shares} users")
        
        # Sync assistant schemas after successful registration (user-scoped)
        # Note: Assistant metadata was already synced in pre-step (line 221) to satisfy FK constraint.
        # We only need to sync schemas here, which may take a moment to become available.
        schemas_warming = False
        try:
            sync_service = get_sync_service()
            user_token = getattr(actor, "access_token", None)

            # Attempt schema sync with bounded retry
            schemas_synced = False
            for attempt, delay in enumerate([0.0, 0.2, 1.0, 2.0], 1):
                if attempt > 1:
                    import asyncio
                    await asyncio.sleep(delay)
                    log.debug(f"Schema sync attempt {attempt} for assistant {request.assistant_id} after {delay}s delay")
                
                try:
                    schemas_synced = await sync_service.sync_assistant_schemas(request.assistant_id, user_token=user_token)
                    if schemas_synced:
                        log.info(f"Schemas synced for assistant {request.assistant_id} on attempt {attempt}")
                        break
                    else:
                        log.debug(f"Schemas unchanged for assistant {request.assistant_id} on attempt {attempt}")
                except Exception as schema_error:
                    log.warning(f"Schema sync attempt {attempt} failed for assistant {request.assistant_id}: {schema_error}")
                    if attempt == 4:  # Last attempt
                        schemas_warming = True
                        log.warning(f"All schema sync attempts failed for assistant {request.assistant_id}, schemas will be available after background sync")
            
            if not schemas_synced and not schemas_warming:
                schemas_warming = True
                log.info(f"Schemas marked as warming for assistant {request.assistant_id}")
                
        except Exception as sync_error:
            log.warning(f"Failed to sync assistant {request.assistant_id} to mirror: {sync_error}")
            schemas_warming = True  # If main sync fails, schemas definitely need warming
            # Don't fail the registration if sync fails
        
        return AssistantDetailsResponse(
            assistant_id=request.assistant_id,
            graph_id=metadata.get("graph_id") if metadata else langgraph_assistant.get("graph_id", "unknown"),
            name=langgraph_assistant.get("name", metadata.get("display_name") if metadata else "Unknown"),
            description=metadata.get("description") if metadata else None,
            owner_id=metadata.get("owner_id", owner_id) if metadata else owner_id,
            owner_display_name=metadata.get("owner_display_name") if metadata else None,
            created_at=metadata.get("created_at").isoformat() if metadata and metadata.get("created_at") else langgraph_assistant.get("created_at", ""),
            updated_at=metadata.get("updated_at").isoformat() if metadata and metadata.get("updated_at") else langgraph_assistant.get("updated_at"),
            user_permission_level="owner" if owner_id == actor.identity else "admin",
            permissions=permissions,
            metadata=langgraph_assistant.get("metadata"),
            config=langgraph_assistant.get("config"),
            schemas_warming=schemas_warming,
            allowed_actions=allowed_actions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to register assistant: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register assistant: {str(e)}"
        )


@router.get("/assistants/{assistant_id}", response_model=AssistantDetailsResponse)
async def get_assistant_details(
    assistant_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> AssistantDetailsResponse:
    """
    Get detailed information about a specific assistant.
    
    Returns assistant details, user's permission level, and for owners,
    the complete list of users with access.
    
    **Authorization:**
    - **Assistant Users**: Can view details for assistants they have access to
    - **Service Accounts**: Can view details for any assistant
    """
    try:
        log.info(f"Getting assistant details for {assistant_id} by {actor.actor_type}:{actor.identity}")
        
        # Get assistant metadata from our database
        metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
        if not metadata and actor.actor_type != "service":
            raise HTTPException(
                status_code=404,
                detail="Assistant not found"
            )
        
        # Check user permission
        if actor.actor_type == "service":
            user_permission_level = "admin"
        else:
            user_permission_level = await AssistantPermissionsManager.get_user_permission_for_assistant(
                actor.identity, assistant_id
            )
            if not user_permission_level:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this assistant"
                )
        
        # Get LangGraph data
        try:
            langgraph_assistant = await langgraph_service._make_request(
                "GET",
                f"assistants/{assistant_id}"
            )
        except Exception as e:
            log.warning(f"Could not get LangGraph data for assistant {assistant_id}: {e}")
            langgraph_assistant = {}
        
        # Get assistant permissions (only for owners and service accounts)
        permissions = []
        if user_permission_level in ["owner", "admin"] or actor.actor_type == "service":
            permissions_data = await AssistantPermissionsManager.get_assistant_permissions(assistant_id)
            permissions = [
                AssistantPermissionInfo(
                    user_id=perm["user_id"],
                    email=perm["email"] or "Unknown",
                    display_name=perm["display_name"] or "Unknown User",
                    permission_level=perm["permission_level"],
                    granted_by=perm["granted_by"],
                    granted_at=perm["created_at"].isoformat() if perm["created_at"] else "Unknown"
                )
                for perm in permissions_data
            ]

        # Get allowed actions (Phase 3: Centralized permissions)
        if actor.actor_type == "service":
            allowed_actions = ["view", "chat", "edit", "delete", "share", "manage_access"]
        else:
            allowed_actions = await PermissionService.get_allowed_actions(
                user_id=actor.identity,
                resource_type="assistant",
                resource_id=assistant_id,
                resource_metadata=langgraph_assistant
            )

        log.info(f"Retrieved assistant details for {assistant_id} with permission level {user_permission_level}")

        return AssistantDetailsResponse(
            assistant_id=assistant_id,
            graph_id=metadata.get("graph_id") if metadata else langgraph_assistant.get("graph_id", "unknown"),
            name=langgraph_assistant.get("name", metadata.get("display_name") if metadata else "Unknown"),
            description=metadata.get("description") if metadata else None,
            owner_id=metadata.get("owner_id", "unknown") if metadata else "unknown",
            owner_display_name=metadata.get("owner_display_name") if metadata else None,
            created_at=metadata.get("created_at").isoformat() if metadata and metadata.get("created_at") else langgraph_assistant.get("created_at", ""),
            updated_at=metadata.get("updated_at").isoformat() if metadata and metadata.get("updated_at") else langgraph_assistant.get("updated_at"),
            user_permission_level=user_permission_level,
            permissions=permissions,
            metadata=langgraph_assistant.get("metadata"),
            config=langgraph_assistant.get("config"),
            allowed_actions=allowed_actions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get assistant details: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get assistant details: {str(e)}"
        )


@router.patch("/assistants/{assistant_id}", response_model=AssistantUpdateResponse)
async def update_assistant(
    assistant_id: str,
    request: AssistantUpdateRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
) -> AssistantUpdateResponse:
    """
    Update an assistant's details.
    
    Allows updating name, description, and configuration.
    Updates both LangGraph and permission database.
    
    **Authorization:**
    - **Assistant Owners**: Can update assistants they own
    - **Service Accounts**: Can update any assistant (must specify owner_id context)
    """
    try:
        log.info(f"Updating assistant {assistant_id} by {actor.actor_type}:{actor.identity}")
        
        # Check user permission
        if actor.actor_type == "service":
            # Service accounts can update any assistant
            pass
        else:
            user_permission_level = await AssistantPermissionsManager.get_user_permission_for_assistant(
                actor.identity, assistant_id
            )
            if user_permission_level != "owner":
                raise HTTPException(
                    status_code=403,
                    detail="Only assistant owners can update assistants"
                )

        # **SECURITY ENFORCEMENT:** Explicit check for default assistant protection
        # Default assistants (metadata._x_oap_is_default === true) cannot be edited
        # See docs/permission-rules.md for rationale
        metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
        if metadata:
            # Check if assistant is marked as default in metadata
            metadata_obj = metadata.get("metadata", {})
            if isinstance(metadata_obj, str):
                try:
                    metadata_obj = json.loads(metadata_obj)
                except:
                    metadata_obj = {}

            is_default = metadata_obj.get("_x_oap_is_default", False)
            if is_default is True or is_default == "true" or is_default == 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot modify default system assistants"
                )

        # Check if assistant exists in LangGraph
        try:
            current_assistant = await langgraph_service._make_request(
                "GET",
                f"assistants/{assistant_id}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=404,
                detail=f"Assistant not found in LangGraph: {str(e)}"
            )
        
        updated_fields = []
        
        # Update LangGraph assistant if name or config changed
        langgraph_updates = {}
        if request.name is not None:
            langgraph_updates["name"] = request.name
            updated_fields.append("name")
        
        if request.config is not None:
            langgraph_updates["config"] = request.config
            updated_fields.append("config")
        
        if langgraph_updates:
            try:
                # Build complete update payload with top-level description (no metadata.description)
                # CRITICAL: Use defensive parsing to prevent double-encoding corruption
                from langconnect.utils.metadata_validation import sanitize_langgraph_payload

                current_metadata = current_assistant.get("metadata", {})
                current_config = current_assistant.get("config", {})
                current_top_level_description = current_assistant.get("description", "")

                update_payload = {
                    "graph_id": current_assistant.get("graph_id"),
                    "config": request.config if request.config is not None else current_config,
                    "metadata": current_metadata,
                    "name": request.name if request.name is not None else current_assistant.get("name", ""),
                    "description": request.description if request.description is not None else current_top_level_description
                }

                # Sanitize payload to prevent double-encoding and character array corruption
                update_payload = sanitize_langgraph_payload(update_payload)

                await langgraph_service._make_request(
                    "PATCH",  # Use PATCH instead of PUT
                    f"assistants/{assistant_id}",
                    data=update_payload
                )
                log.info(f"Updated LangGraph assistant {assistant_id}: {list(langgraph_updates.keys())}")
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to update assistant in LangGraph: {str(e)}"
                )
        
        # No local metadata updates; rely on LangGraph + mirror. Track description change for response messaging.
        if request.description is not None:
            updated_fields.append("description")
        
        
        
        success = len(updated_fields) > 0
        message = f"Successfully updated {', '.join(updated_fields)}" if success else "No changes made"
        
        # Sync assistant to mirror after successful update
        if success:
            try:
                sync_service = get_sync_service()
                await sync_service.sync_assistant(assistant_id)
                log.info(f"Synced assistant {assistant_id} to mirror after update")
            except Exception as sync_error:
                log.warning(f"Failed to sync assistant {assistant_id} to mirror: {sync_error}")
                # Don't fail the update if sync fails
        
        log.info(f"Assistant {assistant_id} update completed: {message}")
        
        return AssistantUpdateResponse(
            assistant_id=assistant_id,
            updated_fields=updated_fields,
            success=success,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to update assistant: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update assistant: {str(e)}"
        )


@router.delete("/assistants/{assistant_id}", response_model=AssistantDeleteResponse)
async def delete_assistant(
    assistant_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
) -> AssistantDeleteResponse:
    """
    Delete an assistant.
    
    Removes the assistant from both LangGraph and the permission system.
    This operation cannot be undone.
    
    **Authorization:**
    - **Assistant Owners**: Can delete assistants they own
    - **Service Accounts**: Can delete any assistant
    """
    try:
        log.info(f"Deleting assistant {assistant_id} by {actor.actor_type}:{actor.identity}")
        
        # Check user permission
        if actor.actor_type == "service":
            # Service accounts can delete any assistant
            pass
        else:
            user_permission_level = await AssistantPermissionsManager.get_user_permission_for_assistant(
                actor.identity, assistant_id
            )
            if user_permission_level != "owner":
                raise HTTPException(
                    status_code=403,
                    detail="Only assistant owners can delete assistants"
                )

        # **SECURITY ENFORCEMENT:** Explicit check for default assistant protection
        # Default assistants (metadata._x_oap_is_default === true) cannot be deleted
        # See docs/permission-rules.md for rationale
        metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
        if metadata:
            # Check if assistant is marked as default in metadata
            metadata_obj = metadata.get("metadata", {})
            if isinstance(metadata_obj, str):
                try:
                    metadata_obj = json.loads(metadata_obj)
                except:
                    metadata_obj = {}

            is_default = metadata_obj.get("_x_oap_is_default", False)
            if is_default is True or is_default == "true" or is_default == 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete default system assistants"
                )
        
        # Delete from LangGraph
        deleted_from_langgraph = False
        try:
            await langgraph_service._make_request(
                "DELETE",
                f"assistants/{assistant_id}"
            )
            deleted_from_langgraph = True
            log.info(f"Deleted assistant {assistant_id} from LangGraph")
        except Exception as e:
            log.warning(f"Failed to delete assistant {assistant_id} from LangGraph: {e}")
        
        # Clean up permissions
        permissions_cleaned = await AssistantPermissionsManager.delete_assistant_permissions(assistant_id)
        
        # Delete metadata
        metadata_deleted = await AssistantPermissionsManager.delete_assistant_metadata(assistant_id)
        
        
        
        success = deleted_from_langgraph and metadata_deleted
        message = "Assistant successfully deleted"
        
        if not deleted_from_langgraph and not metadata_deleted:
            message = "Failed to delete assistant from both LangGraph and database"
        elif not deleted_from_langgraph:
            message = "Assistant deleted from database, but failed to delete from LangGraph"
        elif not metadata_deleted:
            message = "Assistant deleted from LangGraph, but not found in database"
        
        # Remove assistant from mirror after successful deletion
        if deleted_from_langgraph:
            try:
                async with get_db_connection() as conn:
                    # Remove from assistants_mirror and assistant_schemas (cascade)
                    await conn.execute(
                        "DELETE FROM langconnect.assistants_mirror WHERE assistant_id = $1",
                        UUID(assistant_id)
                    )
                    # Increment version to invalidate frontend caches
                    await conn.fetchval("SELECT langconnect.increment_cache_version('assistants')")
                    await conn.fetchval("SELECT langconnect.increment_cache_version('schemas')")
                    
                    # Refresh graph mirror if we had the graph_id
                    if metadata and metadata.get("graph_id"):
                        await conn.fetchval(
                            "SELECT langconnect.refresh_graph_mirror($1)",
                            metadata["graph_id"]
                        )
                
                log.info(f"Removed assistant {assistant_id} from mirror after deletion")
            except Exception as sync_error:
                log.warning(f"Failed to remove assistant {assistant_id} from mirror: {sync_error}")
                # Don't fail the deletion if mirror cleanup fails
        
        log.info(f"Assistant {assistant_id} deletion completed: {message}")
        
        return AssistantDeleteResponse(
            assistant_id=assistant_id,
            deleted_from_langgraph=deleted_from_langgraph,
            permissions_cleaned=permissions_cleaned,
            success=success,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to delete assistant: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete assistant: {str(e)}"
        )


@router.post("/assistants/sync", response_model=Dict[str, Any])
async def sync_assistants_from_langgraph(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)],
) -> Dict[str, Any]:
    """
    Sync existing assistants from LangGraph to our metadata table.
    
    This utility endpoint helps resolve the legacy assistant problem by discovering
    assistants that exist in LangGraph but aren't registered in our permission system.
    It attempts to determine ownership based on LangGraph metadata.
    
    **Authorization:**
    - **Dev Admins**: Can sync all assistants
    - **Service Accounts**: Can sync all assistants  
    - **Regular Users**: 403 Forbidden (too risky for regular users)
    """
    try:
        log.info(f"Starting assistant sync from LangGraph by {actor.actor_type}:{actor.identity}")
        
        # Permission check - only dev_admins or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Only dev_admin users can sync assistants from LangGraph"
                )
        
        # Get all assistants from LangGraph
        assistants_data = await langgraph_service._make_request(
            "POST", 
            "assistants/search", 
            data={"limit": 1000, "offset": 0}
        )
        langgraph_assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
        
        # Get existing registrations
        async with get_db_connection() as conn:
            existing_registrations = await conn.fetch(
                "SELECT assistant_id FROM langconnect.assistants_mirror"
            )
            existing_assistant_ids = {row["assistant_id"] for row in existing_registrations}
        
        # Process unregistered assistants
        sync_results = {
            "total_langgraph_assistants": len(langgraph_assistants),
            "already_registered": len(existing_assistant_ids),
            "sync_attempted": 0,
            "sync_successful": 0,
            "sync_failed": 0,
            "skipped": 0,
            "results": []
        }
        
        for assistant in langgraph_assistants:
            assistant_id = assistant.get("assistant_id")
            if not assistant_id:
                continue
                
            # Skip if already registered
            if assistant_id in existing_assistant_ids:
                sync_results["skipped"] += 1
                continue
            
            sync_results["sync_attempted"] += 1
            
            try:
                # Determine owner from metadata
                metadata = assistant.get("metadata", {})
                owner_id = metadata.get("owner")
                
                if not owner_id:
                    sync_results["sync_failed"] += 1
                    sync_results["results"].append({
                        "assistant_id": assistant_id,
                        "success": False,
                        "error": "No owner found in metadata",
                        "assistant_name": assistant.get("name", "Unknown")
                    })
                    continue
                
                # Verify owner exists in our system
                owner_info = await GraphPermissionsManager.get_user_by_id(owner_id)
                if not owner_info:
                    # Try to create user role if not exists (fallback)
                    await GraphPermissionsManager.ensure_user_role(
                        user_id=owner_id,
                        email=f"unknown_{owner_id}@system.local",
                        display_name=f"User {owner_id}",
                        default_role="user"
                    )
                
                # Register the assistant
                success = await AssistantPermissionsManager.register_assistant(
                    assistant_id=assistant_id,
                    graph_id=assistant.get("graph_id", "unknown"),
                    owner_id=owner_id,
                    display_name=assistant.get("name", f"Assistant {assistant_id}"),
                    description=metadata.get("description")
                )
                
                if success:
                    sync_results["sync_successful"] += 1
                    sync_results["results"].append({
                        "assistant_id": assistant_id,
                        "success": True,
                        "owner_id": owner_id,
                        "assistant_name": assistant.get("name", "Unknown"),
                        "graph_id": assistant.get("graph_id", "unknown")
                    })
                    log.info(f"Successfully synced assistant {assistant_id} owned by {owner_id}")
                else:
                    sync_results["sync_failed"] += 1
                    sync_results["results"].append({
                        "assistant_id": assistant_id,
                        "success": False,
                        "error": "Failed to register in permission system",
                        "assistant_name": assistant.get("name", "Unknown")
                    })
                    
            except Exception as e:
                sync_results["sync_failed"] += 1
                sync_results["results"].append({
                    "assistant_id": assistant_id,
                    "success": False,
                    "error": str(e),
                    "assistant_name": assistant.get("name", "Unknown")
                })
                log.error(f"Failed to sync assistant {assistant_id}: {e}")
        
        
        
        log.info(f"Assistant sync completed: {sync_results['sync_successful']} successful, {sync_results['sync_failed']} failed")
        
        return sync_results
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to sync assistants from LangGraph: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync assistants from LangGraph: {str(e)}"
        ) 