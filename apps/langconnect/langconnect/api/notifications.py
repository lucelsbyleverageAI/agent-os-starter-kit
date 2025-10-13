"""
Notification management endpoints for permission sharing system.
"""

import logging
from typing import Annotated, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.models.agent import (
    NotificationInfo,
    NotificationsListResponse,
    NotificationUnreadCountResponse,
    NotificationActionRequest,
    NotificationActionResponse,
)
 
from langconnect.services.langgraph_integration import get_langgraph_service, LangGraphService
from langconnect.database.notifications import NotificationManager
from langconnect.database.permissions import AssistantPermissionsManager, GraphPermissionsManager
from langconnect.database.connection import get_db_connection

# Set up logging
log = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["Notifications"])


@router.get("/notifications", response_model=NotificationsListResponse)
async def get_user_notifications(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    status: Optional[str] = Query(None, description="Filter by status: pending, accepted, rejected, expired"),
    limit: int = Query(50, description="Maximum number of notifications to return", ge=1, le=100),
    offset: int = Query(0, description="Number of notifications to skip", ge=0)
) -> NotificationsListResponse:
    """
    Get notifications for the authenticated user.
    
    Returns a list of notifications ordered by creation date (newest first).
    Can be filtered by status and supports pagination.
    
    **Authorization:**
    - **All Users**: Can view their own notifications
    - **Service Accounts**: Can view notifications but only for specific users (not supported yet)
    """
    try:
        log.info(f"Getting notifications for {actor.actor_type}:{actor.identity}")
        
        # Service accounts are not currently supported for notifications
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts cannot access notification endpoints"
            )
        
        # Get notifications for the user
        notifications_data = await NotificationManager.get_user_notifications(
            user_id=actor.identity,
            status=status,
            limit=limit,
            offset=offset
        )
        
        # Convert to response models
        notifications = []
        for notification in notifications_data:
            notification_info = NotificationInfo(
                id=str(notification["id"]),
                recipient_user_id=notification["recipient_user_id"],
                type=notification["type"],
                resource_id=notification["resource_id"],
                resource_type=notification["resource_type"],
                permission_level=notification["permission_level"],
                sender_user_id=notification["sender_user_id"],
                sender_display_name=notification["sender_display_name"],
                status=notification["status"],
                created_at=notification["created_at"].isoformat() if notification["created_at"] else "",
                updated_at=notification["updated_at"].isoformat() if notification["updated_at"] else "",
                responded_at=notification["responded_at"].isoformat() if notification["responded_at"] else None,
                expires_at=notification["expires_at"].isoformat() if notification["expires_at"] else "",
                resource_name=notification["resource_name"],
                resource_description=notification["resource_description"]
            )
            notifications.append(notification_info)
        
        # Get pending count
        pending_count = await NotificationManager.get_unread_count(actor.identity)
        
        log.info(f"Retrieved {len(notifications)} notifications for {actor.identity}")
        
        return NotificationsListResponse(
            notifications=notifications,
            total_count=len(notifications),
            pending_count=pending_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get notifications: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get notifications: {str(e)}"
        )


@router.get("/notifications/unread-count", response_model=NotificationUnreadCountResponse)
async def get_unread_notification_count(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)]
) -> NotificationUnreadCountResponse:
    """
    Get the count of unread (pending) notifications for the authenticated user.
    
    This is a lightweight endpoint for displaying notification badges in the UI.
    
    **Authorization:**
    - **All Users**: Can view their own unread count
    - **Service Accounts**: Not supported
    """
    try:
        log.debug(f"Getting unread count for {actor.actor_type}:{actor.identity}")
        
        # Service accounts are not currently supported for notifications
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts cannot access notification endpoints"
            )
        
        # Get unread count
        unread_count = await NotificationManager.get_unread_count(actor.identity)
        
        return NotificationUnreadCountResponse(unread_count=unread_count)
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get unread count: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get unread count: {str(e)}"
        )


@router.post("/notifications/{notification_id}/accept", response_model=NotificationActionResponse)
async def accept_notification(
    notification_id: str,
    request: NotificationActionRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    langgraph_service: Annotated[LangGraphService, Depends(get_langgraph_service)]
) -> NotificationActionResponse:
    """
    Accept a notification and grant the associated permission.
    
    This endpoint will:
    1. Verify the notification belongs to the authenticated user
    2. Check that the notification is still pending
    3. Grant the permission specified in the notification
    4. Mark the notification as accepted
    5. Apply inheritance logic for graph permissions
    
    **Authorization:**
    - **All Users**: Can accept their own notifications
    - **Service Accounts**: Not supported
    """
    try:
        log.info(f"Accepting notification {notification_id} for {actor.actor_type}:{actor.identity}")
        
        # Service accounts are not currently supported for notifications
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts cannot access notification endpoints"
            )
        
        # Get notification details to verify ownership and status
        notification = await NotificationManager.get_notification_by_id(notification_id)
        if not notification:
            raise HTTPException(
                status_code=404,
                detail="Notification not found"
            )
        
        # Verify the notification belongs to the authenticated user
        if str(notification["recipient_user_id"]) != actor.identity:
            raise HTTPException(
                status_code=403,
                detail="You can only accept your own notifications"
            )
        
        # Check if notification is still pending
        if notification["status"] != "pending":
            return NotificationActionResponse(
                notification_id=notification_id,
                action="accepted",
                success=False,
                message=f"Notification already {notification['status']}",
                permission_granted=False
            )
        
        # If assistant invite, verify prerequisite graph access; guide instead of failing
        if notification["resource_type"] == "assistant":
            assistant_id = str(notification["resource_id"])
            graph_id = None
            try:
                async with get_db_connection() as conn:
                    row = await conn.fetchrow(
                        "SELECT graph_id FROM langconnect.assistants_mirror WHERE assistant_id = $1",
                        UUID(assistant_id),
                    )
                    if row:
                        graph_id = row["graph_id"]
            except Exception:
                graph_id = None

            if graph_id:
                has_graph = await GraphPermissionsManager.has_graph_permission(actor.identity, graph_id, "access")
                if not has_graph:
                    # See if a related graph notification already exists from same sender
                    related = await NotificationManager.check_existing_notification(
                        recipient_user_id=actor.identity,
                        resource_id=graph_id,
                        resource_type="graph",
                        sender_user_id=str(notification["sender_user_id"]),
                    )
                    related_id = str(related["id"]) if related else None
                    # If none exists, create one now to guide the user
                    if related_id is None:
                        graph_name = graph_id.replace("_", " ").title()
                        related_id = await NotificationManager.create_notification(
                            recipient_user_id=actor.identity,
                            notification_type="graph_share",
                            resource_id=graph_id,
                            resource_type="graph",
                            permission_level="access",
                            sender_user_id=str(notification["sender_user_id"]),
                            sender_display_name=notification["sender_user_id"],
                            resource_name=graph_name,
                            resource_description=f"Access to {graph_name} graph",
                        )

                    # Do not accept; return guided response
                    return NotificationActionResponse(
                        notification_id=notification_id,
                        action="accepted",
                        success=False,
                        message="Please accept graph access first, then accept this assistant.",
                        permission_granted=False,
                        next_action="accept_graph",
                        requires_graph_first=True,
                        related_graph_notification_id=related_id,
                    )

        # Accept the notification (this will grant the permission)
        success = await NotificationManager.accept_notification(notification_id)

        if success:
            log.info(f"Successfully accepted notification {notification_id}")

            # If this is an assistant notification but the user lacks graph permission, return a guided message
            if notification["resource_type"] == "assistant":
                # Lightweight check: ensure the user has graph access for this assistant
                try:
                    # We can't know graph_id from notification directly; keep guidance generic
                    pass
                except Exception:
                    pass

            return NotificationActionResponse(
                notification_id=notification_id,
                action="accepted",
                success=True,
                message="Notification accepted and permission granted",
                permission_granted=True
            )
        else:
            log.error(f"Failed to accept notification {notification_id}")
            
            return NotificationActionResponse(
                notification_id=notification_id,
                action="accepted",
                success=False,
                message="Failed to accept notification",
                permission_granted=False
            )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to accept notification: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to accept notification: {str(e)}"
        )


@router.post("/notifications/{notification_id}/reject", response_model=NotificationActionResponse)
async def reject_notification(
    notification_id: str,
    request: NotificationActionRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
) -> NotificationActionResponse:
    """
    Reject a notification without granting the associated permission.
    
    This endpoint will:
    1. Verify the notification belongs to the authenticated user
    2. Check that the notification is still pending
    3. Mark the notification as rejected (no permission is granted)
    
    **Authorization:**
    - **All Users**: Can reject their own notifications
    - **Service Accounts**: Not supported
    """
    try:
        log.info(f"Rejecting notification {notification_id} for {actor.actor_type}:{actor.identity}")
        
        # Service accounts are not currently supported for notifications
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts cannot access notification endpoints"
            )
        
        # Get notification details to verify ownership and status
        notification = await NotificationManager.get_notification_by_id(notification_id)
        if not notification:
            raise HTTPException(
                status_code=404,
                detail="Notification not found"
            )
        
        # Verify the notification belongs to the authenticated user
        if str(notification["recipient_user_id"]) != actor.identity:
            raise HTTPException(
                status_code=403,
                detail="You can only reject your own notifications"
            )
        
        # Check if notification is still pending
        if notification["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reject notification with status: {notification['status']}"
            )
        
        # Reject the notification
        success = await NotificationManager.reject_notification(notification_id)
        
        if success:
            
            log.info(f"Successfully rejected notification {notification_id}")
            
            return NotificationActionResponse(
                notification_id=notification_id,
                action="rejected",
                success=True,
                message="Notification rejected",
                permission_granted=False
            )
        else:
            log.error(f"Failed to reject notification {notification_id}")
            
            return NotificationActionResponse(
                notification_id=notification_id,
                action="rejected",
                success=False,
                message="Failed to reject notification",
                permission_granted=False
            )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to reject notification: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reject notification: {str(e)}"
        ) 