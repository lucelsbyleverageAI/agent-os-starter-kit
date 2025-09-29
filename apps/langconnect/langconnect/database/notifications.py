"""
Database manager for notification system.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from langconnect.database.connection import get_db_connection

log = logging.getLogger(__name__)


class NotificationManager:
    """Manager for notification operations."""
    
    @staticmethod
    async def create_notification(
        recipient_user_id: str,
        notification_type: str,
        resource_id: str,
        resource_type: str,
        permission_level: str,
        sender_user_id: str,
        sender_display_name: str,
        resource_name: str,
        resource_description: Optional[str] = None
    ) -> Optional[str]:
        """Create a new notification.
        
        Args:
            recipient_user_id: User who will receive the notification
            notification_type: Type of notification (graph_share, assistant_share, collection_share)
            resource_id: ID of the resource being shared
            resource_type: Type of resource (graph, assistant, collection)
            permission_level: Permission level being offered
            sender_user_id: User who initiated the sharing
            sender_display_name: Display name of the sender
            resource_name: Name of the resource (snapshot for display)
            resource_description: Description of the resource (optional)
            
        Returns:
            Notification ID if created successfully, None otherwise
        """
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    """
                    SELECT langconnect.create_notification(
                        $1, $2::langconnect.notification_type, $3, $4, $5, $6, $7, $8, $9
                    )
                    """,
                    recipient_user_id, notification_type, resource_id, resource_type,
                    permission_level, sender_user_id, sender_display_name, 
                    resource_name, resource_description
                )
                
                if result:
                    log.info(f"Created notification {result} for {recipient_user_id} from {sender_user_id}")
                    return str(result)
                else:
                    log.error("Failed to create notification - no ID returned")
                    return None
                    
        except Exception as e:
            log.error(f"Failed to create notification: {e}")
            return None
    
    @staticmethod
    async def get_user_notifications(
        user_id: str, 
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get notifications for a user.
        
        Args:
            user_id: User to get notifications for
            status: Filter by status (pending, accepted, rejected, expired)
            limit: Maximum number of notifications to return
            offset: Number of notifications to skip
            
        Returns:
            List of notification dictionaries
        """
        try:
            async with get_db_connection() as conn:
                if status:
                    query = """
                        SELECT 
                            id, recipient_user_id, type, resource_id, resource_type,
                            permission_level, sender_user_id, sender_display_name,
                            status, created_at, updated_at, responded_at, expires_at,
                            resource_name, resource_description
                        FROM langconnect.notifications
                        WHERE recipient_user_id = $1 AND status = $2
                        ORDER BY created_at DESC
                        LIMIT $3 OFFSET $4
                    """
                    results = await conn.fetch(query, user_id, status, limit, offset)
                else:
                    query = """
                        SELECT 
                            id, recipient_user_id, type, resource_id, resource_type,
                            permission_level, sender_user_id, sender_display_name,
                            status, created_at, updated_at, responded_at, expires_at,
                            resource_name, resource_description
                        FROM langconnect.notifications
                        WHERE recipient_user_id = $1
                        ORDER BY created_at DESC
                        LIMIT $2 OFFSET $3
                    """
                    results = await conn.fetch(query, user_id, limit, offset)
                
                return [dict(row) for row in results]
                
        except Exception as e:
            log.error(f"Failed to get notifications for user {user_id}: {e}")
            return []
    
    @staticmethod
    async def get_unread_count(user_id: str) -> int:
        """Get count of unread (pending) notifications for a user.
        
        Args:
            user_id: User to get count for
            
        Returns:
            Number of pending notifications
        """
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM langconnect.notifications
                    WHERE recipient_user_id = $1 AND status = 'pending'
                    """,
                    user_id
                )
                return result or 0
                
        except Exception as e:
            log.error(f"Failed to get unread count for user {user_id}: {e}")
            return 0
    
    @staticmethod
    async def get_notification_by_id(notification_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific notification by ID.
        
        Args:
            notification_id: Notification ID
            
        Returns:
            Notification dictionary or None if not found
        """
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT 
                        id, recipient_user_id, type, resource_id, resource_type,
                        permission_level, sender_user_id, sender_display_name,
                        status, created_at, updated_at, responded_at, expires_at,
                        resource_name, resource_description
                    FROM langconnect.notifications
                    WHERE id = $1::uuid
                    """,
                    notification_id
                )
                
                return dict(result) if result else None
                
        except Exception as e:
            log.error(f"Failed to get notification {notification_id}: {e}")
            return None
    
    @staticmethod
    async def accept_notification(notification_id: str) -> bool:
        """Accept a notification and grant the associated permission.
        
        Args:
            notification_id: Notification ID to accept
            
        Returns:
            True if accepted successfully, False otherwise
        """
        try:
            async with get_db_connection() as conn:
                # First get notification details for debugging
                notification = await conn.fetchrow(
                    "SELECT * FROM langconnect.notifications WHERE id = $1::uuid",
                    notification_id
                )
                
                if notification:
                    log.info(f"🔍 NOTIFICATION DEBUG: Accepting notification {notification_id}")
                    log.info(f"  📋 Details: recipient={notification['recipient_user_id']}, type={notification['type']}")
                    log.info(f"  🎯 Resource: {notification['resource_type']} {notification['resource_id']}")
                    log.info(f"  🔐 Permission: {notification['permission_level']}")
                    log.info(f"  👤 Sender: {notification['sender_user_id']}")
                
                result = await conn.fetchval(
                    "SELECT langconnect.accept_notification($1::uuid)",
                    notification_id
                )
                
                if result:
                    log.info(f"✅ NOTIFICATION: Successfully accepted notification {notification_id}")
                    
                    # Debug: Check if permission was actually created
                    if notification and notification['resource_type'] == 'graph':
                        permission_check = await conn.fetchrow(
                            "SELECT * FROM langconnect.graph_permissions WHERE user_id = $1 AND graph_id = $2",
                            str(notification['recipient_user_id']), str(notification['resource_id'])
                        )
                        if permission_check:
                            log.info(f"✅ DB VERIFY: Graph permission created - user {permission_check['user_id']} has {permission_check['permission_level']} on {permission_check['graph_id']}")
                        else:
                            log.error(f"❌ DB VERIFY: Graph permission NOT found after accepting notification!")
                    
                    return True
                else:
                    log.warning(f"❌ NOTIFICATION: Failed to accept notification {notification_id}")
                    return False
                    
        except Exception as e:
            log.error(f"Failed to accept notification {notification_id}: {e}")
            return False
    
    @staticmethod
    async def reject_notification(notification_id: str) -> bool:
        """Reject a notification without granting permission.
        
        Args:
            notification_id: Notification ID to reject
            
        Returns:
            True if rejected successfully, False otherwise
        """
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    "SELECT langconnect.reject_notification($1::uuid)",
                    notification_id
                )
                
                if result:
                    log.info(f"Successfully rejected notification {notification_id}")
                    return True
                else:
                    log.warning(f"Failed to reject notification {notification_id}")
                    return False
                    
        except Exception as e:
            log.error(f"Failed to reject notification {notification_id}: {e}")
            return False
    
    @staticmethod
    async def cleanup_expired_notifications() -> int:
        """Mark expired notifications as expired.
        
        Returns:
            Number of notifications marked as expired
        """
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    "SELECT langconnect.cleanup_expired_notifications()"
                )
                
                expired_count = result or 0
                if expired_count > 0:
                    log.info(f"Marked {expired_count} notifications as expired")
                
                return expired_count
                
        except Exception as e:
            log.error(f"Failed to cleanup expired notifications: {e}")
            return 0
    
    @staticmethod
    async def delete_notification(notification_id: str) -> bool:
        """Delete a notification (admin operation).
        
        Args:
            notification_id: Notification ID to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            async with get_db_connection() as conn:
                result = await conn.execute(
                    "DELETE FROM langconnect.notifications WHERE id = $1::uuid",
                    notification_id
                )
                
                deleted_count = int(result.split()[-1]) if result else 0
                if deleted_count > 0:
                    log.info(f"Deleted notification {notification_id}")
                    return True
                else:
                    log.warning(f"No notification found to delete: {notification_id}")
                    return False
                    
        except Exception as e:
            log.error(f"Failed to delete notification {notification_id}: {e}")
            return False
    
    @staticmethod
    async def check_existing_notification(
        recipient_user_id: str,
        resource_id: str,
        resource_type: str,
        sender_user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Check if a similar pending notification already exists.
        
        Args:
            recipient_user_id: User who would receive the notification
            resource_id: Resource being shared
            resource_type: Type of resource
            sender_user_id: User initiating the share
            
        Returns:
            Existing notification if found, None otherwise
        """
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT 
                        id, recipient_user_id, type, resource_id, resource_type,
                        permission_level, sender_user_id, sender_display_name,
                        status, created_at, updated_at, responded_at, expires_at,
                        resource_name, resource_description
                    FROM langconnect.notifications
                    WHERE recipient_user_id = $1 
                      AND resource_id = $2 
                      AND resource_type = $3 
                      AND sender_user_id = $4
                      AND status = 'pending'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    recipient_user_id, resource_id, resource_type, sender_user_id
                )
                
                return dict(result) if result else None
                
        except Exception as e:
            log.error(f"Failed to check existing notification: {e}")
            return None 