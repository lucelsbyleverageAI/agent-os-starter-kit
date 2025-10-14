"""
Graph permission management endpoints: listing, viewing, granting, and revoking access.
"""

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.models.agent import (
    GraphInfo,
    GraphListResponse,
    UserPermissionInfo,
    GraphPermissionsResponse,
    GrantGraphAccessRequest,
    GrantedPermission,
    GrantGraphAccessResponse,
    RevokeGraphAccessResponse,
)
from langconnect.services.langgraph_integration import get_langgraph_service, LangGraphService

from langconnect.services.permission_service import PermissionService
from langconnect.database.permissions import GraphPermissionsManager
from langconnect.database.notifications import NotificationManager

# Set up logging
log = logging.getLogger(__name__)

# Create router
router = APIRouter()


@router.get("/graphs", response_model=GraphListResponse)
async def list_accessible_graphs(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> GraphListResponse:
    """
    List graphs accessible to the current user.
    
    Returns only graphs that the user has permissions to access,
    along with basic metadata about each graph.
    
    **Authorization:**
    - **All Users**: Can list their accessible graphs
    - **Service Accounts**: Can see all graphs
    """
    try:
        log.info(f"Listing accessible graphs for {actor.actor_type}:{actor.identity}")
        
        # Get user's accessible graphs from permission database
        if actor.actor_type == "service":
            # Service accounts can see all graphs - get from scan
            from langconnect.api.graph_actions.lifecycle import scan_graphs
            scan_result = await scan_graphs(actor, langgraph_service)
            accessible_graph_ids = [g.graph_id for g in scan_result.valid_graphs]
            user_permissions = {}
        else:
            # Regular users - get their specific permissions
            user_graphs = await GraphPermissionsManager.get_user_accessible_graphs(actor.identity)
            accessible_graph_ids = [g["graph_id"] for g in user_graphs]
            user_permissions = {g["graph_id"]: g for g in user_graphs}
        
        if not accessible_graph_ids:
            log.info(f"No accessible graphs found for {actor.actor_type}:{actor.identity}")
            return GraphListResponse(graphs=[], total_count=0)
        
        # Get current graph information from LangGraph
        assistants_data = await langgraph_service._make_request(
            "POST", 
            "assistants/search", 
            data={"limit": 1000, "offset": 0}
        )
        assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
        
        # Group assistants by graph
        assistants_by_graph = {}
        for assistant in assistants:
            graph_id = assistant.get("graph_id")
            if graph_id in accessible_graph_ids:
                if graph_id not in assistants_by_graph:
                    assistants_by_graph[graph_id] = []
                assistants_by_graph[graph_id].append(assistant)
        
        # Build graph info response
        graphs = []
        for graph_id in accessible_graph_ids:
            graph_assistants = assistants_by_graph.get(graph_id, [])
            
            # Check schema accessibility
            schema_accessible = False
            if graph_assistants:
                try:
                    first_assistant_id = graph_assistants[0].get("assistant_id")
                    if first_assistant_id:
                        await langgraph_service._make_request(
                            "GET", 
                            f"assistants/{first_assistant_id}/schemas"
                        )
                        schema_accessible = True
                except Exception:
                    pass
            
            # Check for default assistant
            has_default_assistant = any(
                assistant.get("metadata", {}).get("created_by") == "system" 
                for assistant in graph_assistants
            )
            
            # Get user permission info
            user_permission = user_permissions.get(graph_id)
            permission_level = user_permission.get("permission_level") if user_permission else None
            created_at = user_permission.get("created_at").isoformat() if user_permission and user_permission.get("created_at") else None

            # Get allowed actions (Phase 3: Centralized permissions)
            if actor.actor_type == "service":
                allowed_actions = ["view", "create_assistant", "manage_access"]
            else:
                allowed_actions = await PermissionService.get_allowed_actions(
                    user_id=actor.identity,
                    resource_type="graph",
                    resource_id=graph_id
                )

            graph_info = GraphInfo(
                graph_id=graph_id,
                schema_accessible=schema_accessible,
                assistants_count=len(graph_assistants),
                has_default_assistant=has_default_assistant,
                user_permission_level=permission_level,
                created_at=created_at,
                allowed_actions=allowed_actions
            )
            graphs.append(graph_info)
        
        log.info(f"Listed {len(graphs)} accessible graphs for {actor.actor_type}:{actor.identity}")
        
        # Add targeted debugging for permission data only when needed
        if actor.actor_type == "user" and len(graphs) > 0:
            permission_summary = {g.graph_id: g.user_permission_level for g in graphs}
            log.info(f"🔍 PERMISSION SUMMARY: {permission_summary}")
        
        return GraphListResponse(
            graphs=graphs,
            total_count=len(graphs)
        )
        
    except Exception as e:
        log.error(f"Failed to list accessible graphs: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list accessible graphs: {str(e)}"
        )


@router.get("/graphs/{graph_id}/permissions", response_model=GraphPermissionsResponse)
async def get_graph_permissions(
    graph_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
) -> GraphPermissionsResponse:
    """
    Get all permissions for a specific graph.
    
    Returns list of users who have access to the graph and their permission levels.
    
    **Authorization:**
    - **Graph Admins**: Can view permissions for graphs they admin
    - **Service Accounts**: Can view any graph permissions
    - **Regular Users**: 403 Forbidden
    """
    try:
        log.info(f"Getting permissions for graph {graph_id} by {actor.actor_type}:{actor.identity}")
        
        # Permission check
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role == "dev_admin":
                # Dev admins can see any graph permissions
                pass
            else:
                # Check if user has admin permission on this specific graph
                has_admin = await GraphPermissionsManager.has_graph_permission(
                    actor.identity, graph_id, "admin"
                )
                if not has_admin:
                    raise HTTPException(
                        status_code=403,
                        detail="Only graph admins can view graph permissions"
                    )
        
        # Get graph permissions
        permissions_data = await GraphPermissionsManager.get_graph_permissions(graph_id)
        
        # Convert to response format
        permissions = []
        for perm in permissions_data:
            permission_info = UserPermissionInfo(
                user_id=perm["user_id"],
                email=perm["email"] or "Unknown",
                display_name=perm["display_name"] or "Unknown User",
                permission_level=perm["permission_level"],
                granted_by=perm["granted_by"],
                granted_at=perm["created_at"].isoformat() if perm["created_at"] else "Unknown"
            )
            permissions.append(permission_info)
        
        log.info(f"Retrieved {len(permissions)} permissions for graph {graph_id}")
        
        return GraphPermissionsResponse(
            graph_id=graph_id,
            permissions=permissions,
            total_users=len(permissions)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get graph permissions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get graph permissions: {str(e)}"
        )


@router.post("/graphs/{graph_id}/permissions", response_model=GrantGraphAccessResponse)
async def grant_graph_access(
    graph_id: str,
    request: GrantGraphAccessRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
) -> GrantGraphAccessResponse:
    """
    Grant access to a graph for specified users.
    
    Allows granting admin or access permissions to multiple users at once.
    
    **Authorization:**
    - **Graph Admins**: Can grant access to graphs they admin
    - **Service Accounts**: Can grant access to any graph
    - **Regular Users**: 403 Forbidden
    """
    try:
        log.info(f"Granting graph access to {graph_id} by {actor.actor_type}:{actor.identity}")
        
        # Permission check
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role == "dev_admin":
                # Dev admins can grant access to any graph
                pass
            else:
                # Check if user has admin permission on this specific graph
                has_admin = await GraphPermissionsManager.has_graph_permission(
                    actor.identity, graph_id, "admin"
                )
                if not has_admin:
                    raise HTTPException(
                        status_code=403,
                        detail="Only graph admins can grant graph access"
                    )
        
        # Validate users list
        if not request.users:
            raise HTTPException(
                status_code=400,
                detail="Users list cannot be empty"
            )
        
        # Grant permissions - different logic for service accounts vs users
        permissions_granted = []
        notifications_created = []
        successful_grants = 0
        failed_grants = 0
        errors = []
        
        # Get sender display name for notifications
        sender_display_name = "System"
        if actor.actor_type == "user":
            sender_info = await GraphPermissionsManager.get_user_by_id(actor.identity)
            sender_display_name = sender_info.get("display_name") or sender_info.get("email") or "Unknown User"
        
        for user_request in request.users:
            user_id = user_request.get("user_id")
            permission_level = user_request.get("level", "access")
            
            if not user_id:
                errors.append("Missing user_id in request")
                failed_grants += 1
                continue
            
            if permission_level not in ["admin", "access"]:
                errors.append(f"Invalid permission level '{permission_level}' for user {user_id}")
                failed_grants += 1
                continue
            
            # Check if user exists
            user_info = await GraphPermissionsManager.get_user_by_id(user_id)
            if not user_info:
                errors.append(f"User {user_id} not found")
                failed_grants += 1
                continue
            
            # Check if permission already exists
            existing_permission = await GraphPermissionsManager.has_graph_permission(
                user_id, graph_id, "access"  # Check for any permission
            )
            
            # Check for duplicate pending notifications
            existing_notification = await NotificationManager.check_existing_notification(
                recipient_user_id=user_id,
                resource_id=graph_id,
                resource_type="graph",
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
                    "status": "pending_existing"
                })
                successful_grants += 1
                continue
            
            # Service accounts: direct grant (existing behavior)
            if actor.actor_type == "service":
                success = await GraphPermissionsManager.grant_graph_permission(
                    graph_id=graph_id,
                    user_id=user_id,
                    permission_level=permission_level,
                    granted_by=actor.identity
                )
                
                if success:
                    permissions_granted.append(GrantedPermission(
                        user_id=user_id,
                        email=user_info["email"],
                        permission_level=permission_level,
                        was_updated=existing_permission
                    ))
                    successful_grants += 1
                else:
                    errors.append(f"Failed to grant permission to user {user_id}")
                    failed_grants += 1
            
            # User-to-user sharing: create notification
            else:
                # Get graph display name
                graph_display_name = graph_id.replace('_', ' ').title()
                
                notification_id = await NotificationManager.create_notification(
                    recipient_user_id=user_id,
                    notification_type="graph_share",
                    resource_id=graph_id,
                    resource_type="graph",
                    permission_level=permission_level,
                    sender_user_id=actor.identity,
                    sender_display_name=sender_display_name,
                    resource_name=graph_display_name,
                    resource_description=f"Access to {graph_display_name} graph"
                )
                
                if notification_id:
                    notifications_created.append({
                        "notification_id": notification_id,
                        "user_id": user_id,
                        "email": user_info["email"] or "Unknown",
                        "display_name": user_info["display_name"] or "Unknown User",
                        "permission_level": permission_level,
                        "status": "notification_sent"
                    })
                    successful_grants += 1
                    log.info(f"Created notification {notification_id} for user {user_id}")
                else:
                    errors.append(f"Failed to create notification for user {user_id}")
                    failed_grants += 1
        
        
        
        if actor.actor_type == "service":
            log.info(f"Graph access granted to {graph_id}: {successful_grants} direct grants, {failed_grants} failed")
        else:
            log.info(f"Graph access sharing to {graph_id}: {successful_grants} notifications created, {failed_grants} failed")
        
        return GrantGraphAccessResponse(
            graph_id=graph_id,
            permissions_granted=permissions_granted,
            notifications_created=notifications_created,
            successful_grants=successful_grants,
            failed_grants=failed_grants,
            errors=errors
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to grant graph access: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to grant graph access: {str(e)}"
        )


@router.delete("/graphs/{graph_id}/permissions/{user_id}", response_model=RevokeGraphAccessResponse)
async def revoke_graph_access(
    graph_id: str,
    user_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> RevokeGraphAccessResponse:
    """
    Revoke a user's access to a graph.
    
    Removes the user's permission to access the specified graph.
    
    **Authorization:**
    - **Graph Admins**: Can revoke access from graphs they admin
    - **Service Accounts**: Can revoke access from any graph
    - **Regular Users**: 403 Forbidden
    """
    try:
        log.info(f"Revoking graph access from {graph_id} for user {user_id} by {actor.actor_type}:{actor.identity}")
        
        # Permission logic - check self-revocation FIRST
        if actor.actor_type == "user" and actor.identity == user_id:
            # Self-revocation: Users can revoke their own access, but dev_admins cannot (system protection)
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role == "dev_admin":
                raise HTTPException(
                    status_code=403,
                    detail="Dev admin users cannot revoke their own graph access"
                )
            # Regular users can revoke their own access
            log.info(f"User {user_id} is revoking their own access to graph {graph_id}")
        else:
            # Admin revoking someone else's access - check admin permissions
            if actor.actor_type == "user":
                user_role = await GraphPermissionsManager.get_user_role(actor.identity)
                if user_role == "dev_admin":
                    # Dev admins can revoke access from any graph
                    pass
                else:
                    # Check if user has admin permission on this specific graph
                    has_admin = await GraphPermissionsManager.has_graph_permission(
                        actor.identity, graph_id, "admin"
                    )
                    if not has_admin:
                        raise HTTPException(
                            status_code=403,
                            detail="Only graph admins can revoke graph access"
                        )
        
        # Check if user exists
        user_info = await GraphPermissionsManager.get_user_by_id(user_id)
        if not user_info:
            raise HTTPException(
                status_code=404,
                detail=f"User {user_id} not found"
            )
        
        # Revoke permission
        success = await GraphPermissionsManager.revoke_graph_permission(graph_id, user_id)
        
        # If graph permission was successfully revoked, also clean up assistant permissions
        assistant_permissions_cleaned = 0
        if success:
            try:
                # Get all assistants in this graph that the user has permissions for
                from ...database.permissions import AssistantPermissionsManager
                
                # Get all assistants in the graph from LangGraph
                assistants_data = await langgraph_service._make_request(
                    "POST", 
                    "assistants/search", 
                    data={
                        "limit": 1000,
                        "offset": 0,
                        "sort_by": "created_at",
                        "sort_order": "desc"
                    }
                )
                assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
                
                # Filter assistants that belong to this graph
                graph_assistants = [a for a in assistants if a.get("graph_id") == graph_id]
                
                # Remove user's permissions for all assistants in this graph
                for assistant in graph_assistants:
                    assistant_id = assistant.get("assistant_id")
                    if assistant_id:
                        # Check if user has permission for this assistant
                        user_permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
                            user_id=user_id,
                            assistant_id=assistant_id
                        )
                        
                        if user_permission:
                            # Revoke the assistant permission
                            revoke_success = await AssistantPermissionsManager.revoke_assistant_permission(
                                assistant_id=assistant_id,
                                user_id=user_id
                            )
                            
                            if revoke_success:
                                assistant_permissions_cleaned += 1
                                log.info(f"Cleaned up assistant permission for user {user_id} on assistant {assistant_id} (graph {graph_id})")
                
                if assistant_permissions_cleaned > 0:
                    log.info(f"Cleaned up {assistant_permissions_cleaned} assistant permissions for user {user_id} in graph {graph_id}")
                    
            except Exception as e:
                log.warning(f"Failed to clean up assistant permissions for user {user_id} in graph {graph_id}: {e}")
                # Don't fail the whole operation if assistant cleanup fails
        
        message = f"Access successfully revoked" if success else "No access found to revoke"
        if success and assistant_permissions_cleaned > 0:
            message += f" (cleaned up {assistant_permissions_cleaned} assistant permissions)"
        
        
        
        log.info(f"Graph access revocation for {user_id} on {graph_id}: {message}")
        
        return RevokeGraphAccessResponse(
            graph_id=graph_id,
            user_id=user_id,
            revoked=success,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to revoke graph access: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to revoke graph access: {str(e)}"
        ) 