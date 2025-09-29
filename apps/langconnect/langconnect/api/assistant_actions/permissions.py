"""
Assistant permission management endpoints: sharing, revoking access, and viewing permissions.
"""

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.models.agent import (
    ShareAssistantRequest,
    SharedUser,
    ShareAssistantResponse,
    RevokeAssistantAccessResponse,
    AssistantPermissionsResponse,
    AssistantPermissionInfo,
)
from langconnect.services.langgraph_integration import get_langgraph_service, LangGraphService
 
from langconnect.database.permissions import GraphPermissionsManager, AssistantPermissionsManager
from langconnect.database.notifications import NotificationManager
from langconnect.database.connection import get_db_connection

# Set up logging
log = logging.getLogger(__name__)

# Create router
router = APIRouter()


@router.post("/assistants/{assistant_id}/share", response_model=ShareAssistantResponse)
async def share_assistant(
    assistant_id: str,
    request: ShareAssistantRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
) -> ShareAssistantResponse:
    """
    Share an assistant with specified users.
    
    Allows granting access to multiple users at once. Users must have access to
    the graph that the assistant belongs to in order to be granted assistant access.
    
    **Authorization:**
    - **Assistant Owners**: Can share assistants they own
    - **Service Accounts**: Can share any assistant
    """
    try:
        log.info(f"Sharing assistant {assistant_id} by {actor.actor_type}:{actor.identity}")
        
        # Check user permission (only owners can share)
        if actor.actor_type == "service":
            # Service accounts can share any assistant
            pass
        else:
            user_permission_level = await AssistantPermissionsManager.get_user_permission_for_assistant(
                actor.identity, assistant_id
            )
            if user_permission_level != "owner":
                raise HTTPException(
                    status_code=403,
                    detail="Only assistant owners can share assistants"
                )
        
        # Get assistant metadata to verify it exists and get graph_id
        metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
        if not metadata:
            raise HTTPException(
                status_code=404,
                detail="Assistant not found"
            )
        
        graph_id = metadata.get("graph_id")
        if not graph_id:
            raise HTTPException(
                status_code=500,
                detail="Assistant has no associated graph"
            )
        
        # Validate users list
        if not request.users:
            raise HTTPException(
                status_code=400,
                detail="Users list cannot be empty"
            )
        
        # Share with users - different logic for service accounts vs users
        users_shared = []
        notifications_created = []
        successful_shares = 0
        failed_shares = 0
        errors = []
        
        # Get sender display name for notifications
        sender_display_name = "System"
        if actor.actor_type == "user":
            sender_info = await GraphPermissionsManager.get_user_by_id(actor.identity)
            sender_display_name = sender_info.get("display_name") or sender_info.get("email") or "Unknown User"
        
        for user_request in request.users:
            user_id = user_request.user_id
            permission_level = user_request.permission_level or "viewer"
            
            if permission_level not in ["editor", "viewer"]:
                errors.append(f"Invalid permission level '{permission_level}' for user {user_id}")
                failed_shares += 1
                continue
            
            try:
                # Check if user exists
                user_info = await GraphPermissionsManager.get_user_by_id(user_id)
                if not user_info:
                    errors.append(f"User {user_id} not found")
                    failed_shares += 1
                    continue
                
                # Check if user has graph access; if missing, orchestrate a graph invite instead of erroring
                has_graph_access = await GraphPermissionsManager.has_graph_permission(
                    user_id, graph_id, "access"
                )
                graph_notification_id: str | None = None
                if not has_graph_access and actor.actor_type == "user":
                    # Idempotently create a graph_share notification (or reuse existing)
                    existing_graph_notif = await NotificationManager.check_existing_notification(
                        recipient_user_id=user_id,
                        resource_id=graph_id,
                        resource_type="graph",
                        sender_user_id=actor.identity,
                    )
                    if existing_graph_notif:
                        graph_notification_id = str(existing_graph_notif["id"])
                    else:
                        # Derive a human-friendly name for the graph
                        graph_display_name = (graph_id or "").replace("_", " ").title()
                        graph_notification_id = await NotificationManager.create_notification(
                            recipient_user_id=user_id,
                            notification_type="graph_share",
                            resource_id=graph_id,
                            resource_type="graph",
                            permission_level="access",
                            sender_user_id=actor.identity,
                            sender_display_name=sender_display_name,
                            resource_name=graph_display_name,
                            resource_description=f"Access to {graph_display_name} graph"
                        )
                
                # Check if permission already exists
                existing_permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                    user_id, assistant_id
                )
                
                # Skip if user is already the owner
                if existing_permission == "owner":
                    errors.append(f"User {user_id} is already the owner of this assistant")
                    failed_shares += 1
                    continue
                
                # Check for duplicate pending notifications
                existing_notification = await NotificationManager.check_existing_notification(
                    recipient_user_id=user_id,
                    resource_id=assistant_id,
                    resource_type="assistant",
                    sender_user_id=actor.identity
                )
                
                if existing_notification and existing_notification.get("status") == "pending":
                    # Treat duplicate invite as benign
                    notifications_created.append({
                        "notification_id": str(existing_notification["id"]),
                        "user_id": user_id,
                        "email": user_info["email"] or "Unknown",
                        "display_name": user_info["display_name"] or "Unknown User",
                        "permission_level": permission_level,
                        "status": "pending_existing",
                        "requires_graph_first": not has_graph_access,
                        "graph_notification_id": graph_notification_id,
                    })
                    successful_shares += 1
                    continue
                
                # Service accounts: direct grant (existing behavior)
                if actor.actor_type == "service":
                    success = await AssistantPermissionsManager.grant_assistant_permission(
                        assistant_id=assistant_id,
                        user_id=user_id,
                        permission_level=permission_level,
                        granted_by=actor.identity
                    )
                    
                    if success:
                        users_shared.append(SharedUser(
                            user_id=user_id,
                            email=user_info["email"] or "Unknown",
                            display_name=user_info["display_name"] or "Unknown User",
                            permission_level=permission_level,
                            was_updated=existing_permission is not None
                        ))
                        successful_shares += 1
                    else:
                        errors.append(f"Failed to grant permission to user {user_id}")
                        failed_shares += 1
                
                # User-to-user sharing: create notification (orchestrated with graph invite if needed)
                else:
                    # If user already has assistant permission, treat as already granted
                    if existing_permission in ["viewer", "editor", "owner"]:
                        notifications_created.append({
                            "notification_id": None,
                            "user_id": user_id,
                            "email": user_info["email"] or "Unknown",
                            "display_name": user_info["display_name"] or "Unknown User",
                            "permission_level": existing_permission,
                            "status": "already_granted"
                        })
                        successful_shares += 1
                        continue

                    notification_id = await NotificationManager.create_notification(
                        recipient_user_id=user_id,
                        notification_type="assistant_share",
                        resource_id=assistant_id,
                        resource_type="assistant",
                        permission_level=permission_level,
                        sender_user_id=actor.identity,
                        sender_display_name=sender_display_name,
                        resource_name=metadata.get("display_name") or "Unknown Assistant",
                        resource_description=metadata.get("description")
                    )
                    
                    if notification_id:
                        notifications_created.append({
                            "notification_id": notification_id,
                            "user_id": user_id,
                            "email": user_info["email"] or "Unknown",
                            "display_name": user_info["display_name"] or "Unknown User",
                            "permission_level": permission_level,
                            "status": "notification_sent",
                            "requires_graph_first": not has_graph_access,
                            "graph_notification_id": graph_notification_id,
                        })
                        successful_shares += 1
                        log.info(f"Created notification {notification_id} for user {user_id}")
                    else:
                        errors.append(f"Failed to create notification for user {user_id}")
                        failed_shares += 1
                    
            except Exception as e:
                errors.append(f"Error sharing with user {user_id}: {str(e)}")
                failed_shares += 1
                log.error(f"Error sharing assistant {assistant_id} with user {user_id}: {e}")
        
        
        
        if actor.actor_type == "service":
            log.info(f"Assistant {assistant_id} sharing completed: {successful_shares} direct grants, {failed_shares} failed")
        else:
            log.info(f"Assistant {assistant_id} sharing completed: {successful_shares} notifications created, {failed_shares} failed")
        
        return ShareAssistantResponse(
            assistant_id=assistant_id,
            users_shared=users_shared,
            notifications_created=notifications_created,
            successful_shares=successful_shares,
            failed_shares=failed_shares,
            errors=errors
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to share assistant: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to share assistant: {str(e)}"
        )


@router.delete("/assistants/{assistant_id}/permissions/{user_id}", response_model=RevokeAssistantAccessResponse)
async def revoke_assistant_access(
    assistant_id: str,
    user_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
) -> RevokeAssistantAccessResponse:
    """
    Revoke a user's access to an assistant.
    
    Removes the user's permission to access the specified assistant.
    Owners cannot revoke access from themselves.
    
    **Authorization:**
    - **Assistant Owners**: Can revoke access from assistants they own
    - **Service Accounts**: Can revoke access from any assistant
    """
    try:
        log.info(f"Revoking assistant access from {assistant_id} for user {user_id} by {actor.actor_type}:{actor.identity}")
        
        # Check user permission (owners can revoke anyone's access, users can revoke their own access)
        if actor.actor_type == "service":
            # Service accounts can revoke access from any assistant
            pass
        else:
            user_permission_level = await AssistantPermissionsManager.get_user_permission_for_assistant(
                actor.identity, assistant_id
            )
            
            # Allow owners to revoke anyone's access, or users to revoke their own access
            if user_permission_level != "owner" and user_id != actor.identity:
                raise HTTPException(
                    status_code=403,
                    detail="You can only revoke your own access or you must be the assistant owner"
                )
        
        # Get assistant metadata to verify it exists
        metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
        if not metadata:
            raise HTTPException(
                status_code=404,
                detail="Assistant not found"
            )
        
        # Check if user exists
        user_info = await GraphPermissionsManager.get_user_by_id(user_id)
        if not user_info:
            raise HTTPException(
                status_code=404,
                detail=f"User {user_id} not found"
            )
        
        # Check if user has permission
        existing_permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
            user_id, assistant_id
        )

        # Prevent revoking access from any owner (unless service account)
        if existing_permission == "owner" and actor.actor_type != "service":
            raise HTTPException(
                status_code=400,
                detail="Cannot revoke access from an assistant owner. Use delete or transfer ownership instead."
            )
        
        success = False
        message = "No access found to revoke"
        
        if existing_permission:
            # Use permission manager to enforce owner/system rules
            try:
                success = await AssistantPermissionsManager.revoke_assistant_permission(assistant_id, user_id)
                message = "Access successfully revoked" if success else "Failed to revoke access"
            except Exception as e:
                log.error(f"Failed to revoke assistant permission: {e}")
                message = f"Failed to revoke access: {str(e)}"
        
        
        
        log.info(f"Assistant access revocation for {user_id} on {assistant_id}: {message}")
        
        return RevokeAssistantAccessResponse(
            assistant_id=assistant_id,
            user_id=user_id,
            revoked=success,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to revoke assistant access: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to revoke assistant access: {str(e)}"
        )


@router.get("/assistants/{assistant_id}/permissions", response_model=AssistantPermissionsResponse)
async def get_assistant_permissions(
    assistant_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> AssistantPermissionsResponse:
    """
    Get sharing details for an assistant.
    
    Returns the complete list of users who have access to the assistant
    and their permission levels. Only accessible to assistant owners.
    
    **Authorization:**
    - **Assistant Owners**: Can view sharing details for assistants they own
    - **Service Accounts**: Can view sharing details for any assistant
    """
    try:
        log.info(f"Getting assistant permissions for {assistant_id} by {actor.actor_type}:{actor.identity}")
        
        # Check user permission (only owners can view permissions)
        if actor.actor_type == "service":
            # Service accounts can view any assistant permissions
            pass
        else:
            user_permission_level = await AssistantPermissionsManager.get_user_permission_for_assistant(
                actor.identity, assistant_id
            )
            if user_permission_level != "owner":
                raise HTTPException(
                    status_code=403,
                    detail="Only assistant owners can view assistant permissions"
                )
        
        # Get assistant metadata
        metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
        if not metadata:
            raise HTTPException(
                status_code=404,
                detail="Assistant not found"
            )
        
        # Get LangGraph data for assistant name
        assistant_name = metadata.get("display_name", "Unknown Assistant")
        try:
            langgraph_assistant = await langgraph_service._make_request(
                "GET",
                f"assistants/{assistant_id}"
            )
            assistant_name = langgraph_assistant.get("name", assistant_name)
        except Exception:
            pass  # Use fallback name if LangGraph request fails
        
        # Get all permissions
        permissions_data = await AssistantPermissionsManager.get_assistant_permissions(assistant_id)
        
        permissions = []
        owner_found = False
        shared_users = 0
        owner_count = 0
        
        for perm in permissions_data:
            permission_info = AssistantPermissionInfo(
                user_id=perm["user_id"],
                email=perm["email"] or "Unknown",
                display_name=perm["display_name"] or "Unknown User",
                permission_level=perm["permission_level"],
                granted_by=perm["granted_by"],
                granted_at=perm["created_at"].isoformat() if perm["created_at"] else "Unknown"
            )
            permissions.append(permission_info)
            
            if perm["permission_level"] == "owner":
                owner_found = True
                owner_count += 1
            else:
                shared_users += 1
        
        log.info(f"Retrieved {len(permissions)} permissions for assistant {assistant_id}")
        
        return AssistantPermissionsResponse(
            assistant_id=assistant_id,
            assistant_name=assistant_name,
            owner_id=metadata.get("owner_id", "unknown"),
            owner_display_name=metadata.get("owner_display_name"),
            permissions=permissions,
            total_users=len(permissions),
            shared_users=shared_users
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get assistant permissions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get assistant permissions: {str(e)}"
        ) 