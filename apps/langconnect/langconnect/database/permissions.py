"""
Database manager for agent permission system.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from langconnect.database.connection import get_db_connection

log = logging.getLogger(__name__)


class GraphPermissionsManager:
    """Manager for graph-level permissions."""
    
    @staticmethod
    async def get_user_role(user_id: str) -> Optional[str]:
        """Get user role from database."""
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchrow(
                    "SELECT role FROM langconnect.user_roles WHERE user_id = $1",
                    user_id
                )
                return result["role"] if result else None
        except Exception as e:
            log.error(f"Failed to get user role for {user_id}: {e}")
            return None
    
    @staticmethod
    async def ensure_user_role(user_id: str, email: str, display_name: str, default_role: str = "user") -> str:
        """Ensure user has a role in the system, creating one if needed."""
        try:
            async with get_db_connection() as conn:
                # Check if user role exists
                existing_role = await conn.fetchval(
                    "SELECT role FROM langconnect.user_roles WHERE user_id = $1",
                    user_id
                )
                
                if existing_role:
                    return existing_role
                
                # Create new user role
                await conn.execute(
                    """
                    INSERT INTO langconnect.user_roles (user_id, role, email, display_name, assigned_by)
                    VALUES ($1, $2, $3, $4, 'system')
                    """,
                    user_id, default_role, email, display_name
                )
                
                log.info(f"Created new user role: {user_id} -> {default_role}")
                return default_role
                
        except Exception as e:
            log.error(f"Failed to ensure user role for {user_id}: {e}")
            raise
    
    @staticmethod
    async def get_all_dev_admins() -> List[Dict[str, Any]]:
        """Get all users with dev_admin role."""
        try:
            async with get_db_connection() as conn:
                results = await conn.fetch(
                    """
                    SELECT user_id, email, display_name, role, created_at
                    FROM langconnect.user_roles 
                    WHERE role = 'dev_admin'
                    ORDER BY created_at ASC
                    """
                )
                return [dict(row) for row in results]
        except Exception as e:
            log.error(f"Failed to get dev admins: {e}")
            return []
    
    @staticmethod
    async def has_graph_permission(user_id: str, graph_id: str, required_level: str = "access") -> bool:
        """Check if user has required permission level for a graph."""
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT permission_level 
                    FROM langconnect.graph_permissions 
                    WHERE user_id = $1 AND graph_id = $2
                    """,
                    user_id, graph_id
                )
                
                if not result:
                    return False
                
                user_level = result["permission_level"]
                
                # Admin permission includes access
                if required_level == "access":
                    return user_level in ["access", "admin"]
                elif required_level == "admin":
                    return user_level == "admin"
                
                return False
                
        except Exception as e:
            log.error(f"Failed to check graph permission for {user_id} on {graph_id}: {e}")
            return False
    
    @staticmethod
    async def grant_graph_permission(
        graph_id: str, 
        user_id: str, 
        permission_level: str, 
        granted_by: str
    ) -> bool:
        """Grant graph permission to a user.
        Use 'system:public' for granted_by when materialising public permissions.
        """
        try:
            async with get_db_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO langconnect.graph_permissions 
                    (graph_id, user_id, permission_level, granted_by)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (graph_id, user_id) 
                    DO UPDATE SET 
                        permission_level = EXCLUDED.permission_level,
                        granted_by = EXCLUDED.granted_by,
                        updated_at = NOW()
                    """,
                    graph_id, user_id, permission_level, granted_by
                )
                
                log.info(f"Granted {permission_level} permission on {graph_id} to {user_id} by {granted_by}")
                return True
                
        except Exception as e:
            log.error(f"Failed to grant graph permission: {e}")
            return False
    
    @staticmethod
    async def get_orphaned_assistants_for_graph(graph_id: str) -> List[Dict[str, Any]]:
        """Get assistants in our database that belong to a specific graph.

        Uses assistants_mirror for graph linkage; derives owner from assistant_permissions.
        """
        try:
            async with get_db_connection() as conn:
                results = await conn.fetch(
                    """
                    SELECT 
                        am.assistant_id,
                        am.graph_id,
                        am.name as display_name,
                        owner_perm.user_id as owner_id,
                        COUNT(ap.user_id) as permission_count
                    FROM langconnect.assistants_mirror am
                    LEFT JOIN langconnect.assistant_permissions ap ON am.assistant_id = ap.assistant_id
                    LEFT JOIN LATERAL (
                        SELECT user_id
                        FROM langconnect.assistant_permissions p
                        WHERE p.assistant_id = am.assistant_id AND p.permission_level = 'owner'
                        ORDER BY p.created_at ASC
                        LIMIT 1
                    ) AS owner_perm ON TRUE
                    WHERE am.graph_id = $1
                    GROUP BY am.assistant_id, am.graph_id, am.name, owner_perm.user_id
                    """,
                    graph_id
                )
                return [dict(row) for row in results]
        except Exception as e:
            log.error(f"Failed to get orphaned assistants for graph {graph_id}: {e}")
            return []
    
    @staticmethod
    async def cleanup_graph_permissions(graph_id: str, dry_run: bool = False) -> int:
        """Remove all permissions for a specific graph."""
        try:
            async with get_db_connection() as conn:
                if dry_run:
                    # Count what would be deleted
                    result = await conn.fetchval(
                        "SELECT COUNT(*) FROM langconnect.graph_permissions WHERE graph_id = $1",
                        graph_id
                    )
                    return result or 0
                else:
                    # Actually delete
                    result = await conn.execute(
                        "DELETE FROM langconnect.graph_permissions WHERE graph_id = $1",
                        graph_id
                    )
                    deleted_count = int(result.split()[-1]) if result else 0
                    log.info(f"Cleaned up {deleted_count} graph permissions for {graph_id}")
                    return deleted_count
        except Exception as e:
            log.error(f"Failed to cleanup graph permissions for {graph_id}: {e}")
            return 0
    
    @staticmethod
    async def cleanup_assistant_permissions_for_graph(graph_id: str, dry_run: bool = False) -> int:
        """Remove assistant permissions for assistants belonging to a specific graph."""
        try:
            async with get_db_connection() as conn:
                if dry_run:
                    # Count what would be deleted using assistants_mirror for graph linkage
                    result = await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM langconnect.assistant_permissions ap
                        JOIN langconnect.assistants_mirror am ON ap.assistant_id = am.assistant_id
                        WHERE am.graph_id = $1
                        """,
                        graph_id
                    )
                    return result or 0
                else:
                    # Actually delete using assistants_mirror for graph linkage
                    result = await conn.execute(
                        """
                        DELETE FROM langconnect.assistant_permissions 
                        WHERE assistant_id IN (
                            SELECT am.assistant_id
                            FROM langconnect.assistants_mirror am
                            WHERE am.graph_id = $1
                        )
                        """,
                        graph_id
                    )
                    deleted_count = int(result.split()[-1]) if result else 0
                    log.info(f"Cleaned up {deleted_count} assistant permissions for graph {graph_id}")
                    return deleted_count
        except Exception as e:
            log.error(f"Failed to cleanup assistant permissions for graph {graph_id}: {e}")
            return 0
    
    @staticmethod
    async def cleanup_assistant_metadata_for_graph(graph_id: str, dry_run: bool = False) -> int:
        """No-op: assistant_metadata has been removed."""
        log.info(f"assistant_metadata cleanup skipped for graph {graph_id} (table removed)")
        return 0
    
    @staticmethod
    async def get_user_accessible_graphs(user_id: str) -> List[Dict[str, Any]]:
        """Get all graphs that a user has access to."""
        try:
            async with get_db_connection() as conn:
                results = await conn.fetch(
                    """
                    SELECT 
                        gp.graph_id,
                        gp.permission_level,
                        gp.created_at,
                        gp.granted_by
                    FROM langconnect.graph_permissions gp
                    WHERE gp.user_id = $1
                    ORDER BY gp.created_at ASC
                    """,
                    user_id
                )
                
                result_list = [dict(row) for row in results]
                
                # Compact debug log for database permissions
                if result_list:
                    permissions_summary = {g['graph_id']: g['permission_level'] for g in result_list}
                    log.info(f"🔍 DB PERMISSIONS: User {user_id} has {len(result_list)} graph permissions: {permissions_summary}")
                else:
                    log.info(f"🔍 DB PERMISSIONS: User {user_id} has no graph permissions")
                
                return result_list
        except Exception as e:
            log.error(f"Failed to get accessible graphs for user {user_id}: {e}")
            return []
    
    @staticmethod
    async def get_graph_permissions(graph_id: str) -> List[Dict[str, Any]]:
        """Get all users who have access to a specific graph."""
        try:
            async with get_db_connection() as conn:
                results = await conn.fetch(
                    """
                    SELECT 
                        gp.user_id,
                        gp.permission_level,
                        gp.granted_by,
                        gp.created_at,
                        ur.email,
                        ur.display_name
                    FROM langconnect.graph_permissions gp
                    LEFT JOIN langconnect.user_roles ur ON gp.user_id = ur.user_id
                    WHERE gp.graph_id = $1
                    ORDER BY gp.created_at ASC
                    """,
                    graph_id
                )
                return [dict(row) for row in results]
        except Exception as e:
            log.error(f"Failed to get graph permissions for {graph_id}: {e}")
            return []
    
    @staticmethod
    async def revoke_graph_permission(graph_id: str, user_id: str) -> bool:
        """Revoke a user's access to a graph."""
        try:
            async with get_db_connection() as conn:
                result = await conn.execute(
                    "DELETE FROM langconnect.graph_permissions WHERE graph_id = $1 AND user_id = $2",
                    graph_id, user_id
                )
                deleted_count = int(result.split()[-1]) if result else 0
                
                if deleted_count > 0:
                    log.info(f"Revoked graph permission for user {user_id} on graph {graph_id}")
                    return True
                else:
                    log.warning(f"No permission found to revoke for user {user_id} on graph {graph_id}")
                    return False
        except Exception as e:
            log.error(f"Failed to revoke graph permission: {e}")
            return False
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information by ID."""
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchrow(
                    "SELECT user_id, email, display_name, role FROM langconnect.user_roles WHERE user_id = $1",
                    user_id
                )
                return dict(result) if result else None
        except Exception as e:
            log.error(f"Failed to get user {user_id}: {e}")
            return None

    @staticmethod
    async def debug_user_permissions(user_id: str) -> Dict[str, Any]:
        """Debug utility to show all permissions for a user.
        
        Args:
            user_id: User to debug permissions for
            
        Returns:
            Dictionary with all permissions for the user
        """
        try:
            async with get_db_connection() as conn:
                # Get graph permissions
                graph_perms = await conn.fetch(
                    """
                    SELECT graph_id, permission_level, granted_by, created_at
                    FROM langconnect.graph_permissions
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    """,
                    user_id
                )
                
                # Get assistant permissions
                assistant_perms = await conn.fetch(
                    """
                    SELECT assistant_id, permission_level, granted_by, created_at
                    FROM langconnect.assistant_permissions
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    """,
                    user_id
                )
                
                # Get user role
                user_role = await conn.fetchrow(
                    """
                    SELECT role, email, display_name, created_at
                    FROM langconnect.user_roles
                    WHERE user_id = $1
                    """,
                    user_id
                )
                
                return {
                    "user_id": user_id,
                    "user_role": dict(user_role) if user_role else None,
                    "graph_permissions": [dict(row) for row in graph_perms],
                    "assistant_permissions": [dict(row) for row in assistant_perms],
                    "total_graph_permissions": len(graph_perms),
                    "total_assistant_permissions": len(assistant_perms)
                }
                
        except Exception as e:
            log.error(f"Failed to debug user permissions for {user_id}: {e}")
            return {
                "user_id": user_id,
                "error": str(e)
            }


class AssistantPermissionsManager:
    """Manager for assistant-level permissions."""
    
    @staticmethod
    async def register_assistant(
        assistant_id: str,
        graph_id: str,
        owner_id: str,
        display_name: str,
        description: Optional[str] = None
    ) -> bool:
        """Register assistant owner permission only (metadata removed)."""
        try:
            async with get_db_connection() as conn:
                # Start transaction
                async with conn.transaction():
                    # Ensure the owner exists in user_roles to satisfy FK constraints
                    await conn.execute(
                        """
                        INSERT INTO langconnect.user_roles (user_id, role, email, display_name, assigned_by)
                        VALUES ($1, 'user', NULL, NULL, 'system:assistant_registration')
                        ON CONFLICT (user_id) DO NOTHING
                        """,
                        owner_id
                    )

                    # Grant owner permission
                    await conn.execute(
                        """
                        INSERT INTO langconnect.assistant_permissions 
                        (assistant_id, user_id, permission_level, granted_by)
                        VALUES ($1, $2, 'owner', $3)
                        ON CONFLICT (assistant_id, user_id) 
                        DO UPDATE SET
                            permission_level = 'owner',
                            updated_at = NOW()
                        """,
                        assistant_id, owner_id, owner_id
                    )
                
                log.info(f"Registered assistant {assistant_id} owned by {owner_id}")
                return True
                
        except Exception as e:
            log.error(f"Failed to register assistant {assistant_id}: {e}")
            return False
    
    @staticmethod
    async def get_user_accessible_assistants(user_id: str) -> List[Dict[str, Any]]:
        """Get all assistants that a user has access to."""
        try:
            async with get_db_connection() as conn:
                results = await conn.fetch(
                    """
                    SELECT 
                        ap.assistant_id,
                        ap.permission_level,
                        ap.created_at as permission_granted_at,
                        am.graph_id,
                        am.name as display_name,
                        am.description,
                        owner_perm.user_id as owner_id,
                        am.langgraph_created_at as assistant_created_at,
                        am.langgraph_updated_at as assistant_updated_at,
                        owner_ur.display_name as owner_display_name
                    FROM langconnect.assistant_permissions ap
                    JOIN langconnect.assistants_mirror am ON ap.assistant_id = am.assistant_id
                    LEFT JOIN LATERAL (
                        SELECT user_id
                        FROM langconnect.assistant_permissions p
                        WHERE p.assistant_id = am.assistant_id AND p.permission_level = 'owner'
                        ORDER BY p.created_at ASC
                        LIMIT 1
                    ) AS owner_perm ON TRUE
                    LEFT JOIN langconnect.user_roles owner_ur ON owner_perm.user_id = owner_ur.user_id
                    WHERE ap.user_id = $1
                    ORDER BY ap.created_at DESC
                    """,
                    user_id
                )
                return [dict(row) for row in results]
        except Exception as e:
            log.error(f"Failed to get accessible assistants for user {user_id}: {e}")
            return []
    
    @staticmethod
    async def get_assistant_metadata(assistant_id: str) -> Optional[Dict[str, Any]]:
        """Get assistant info from mirror, with owner derived from permissions.

        Returns a structure compatible with previous metadata usage.
        """
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT 
                        am.assistant_id,
                        am.graph_id,
                        am.name as display_name,
                        am.description,
                        owner_perm.user_id as owner_id,
                        am.langgraph_created_at as created_at,
                        am.langgraph_updated_at as updated_at,
                        owner_ur.display_name as owner_display_name,
                        owner_ur.email as owner_email
                    FROM langconnect.assistants_mirror am
                    LEFT JOIN LATERAL (
                        SELECT user_id
                        FROM langconnect.assistant_permissions p
                        WHERE p.assistant_id = am.assistant_id AND p.permission_level = 'owner'
                        ORDER BY p.created_at ASC
                        LIMIT 1
                    ) AS owner_perm ON TRUE
                    LEFT JOIN langconnect.user_roles owner_ur ON owner_perm.user_id = owner_ur.user_id
                    WHERE am.assistant_id = $1::uuid
                    """,
                    assistant_id
                )
                return dict(result) if result else None
        except Exception as e:
            log.error(f"Failed to get assistant metadata for {assistant_id}: {e}")
            return None
    
    @staticmethod
    async def get_user_permission_for_assistant(user_id: str, assistant_id: str) -> Optional[str]:
        """Get user's permission level for a specific assistant."""
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    """
                    SELECT permission_level 
                    FROM langconnect.assistant_permissions 
                    WHERE user_id = $1 AND assistant_id = $2
                    """,
                    user_id, assistant_id
                )
                return result
        except Exception as e:
            log.error(f"Failed to get user permission for assistant {assistant_id}: {e}")
            return None
    
    @staticmethod
    async def get_assistant_permissions(assistant_id: str) -> List[Dict[str, Any]]:
        """Get all users who have access to a specific assistant."""
        try:
            async with get_db_connection() as conn:
                results = await conn.fetch(
                    """
                    SELECT 
                        ap.user_id,
                        ap.permission_level,
                        ap.granted_by,
                        ap.created_at,
                        ur.email,
                        ur.display_name
                    FROM langconnect.assistant_permissions ap
                    LEFT JOIN langconnect.user_roles ur ON ap.user_id = ur.user_id
                    WHERE ap.assistant_id = $1
                    ORDER BY ap.created_at ASC
                    """,
                    assistant_id
                )
                return [dict(row) for row in results]
        except Exception as e:
            log.error(f"Failed to get assistant permissions for {assistant_id}: {e}")
            return []
    
    @staticmethod
    async def grant_assistant_permission(
        assistant_id: str,
        user_id: str,
        permission_level: str,
        granted_by: str
    ) -> bool:
        """Grant permission to an assistant for a specific user."""
        # Validate permission level
        if permission_level not in ['owner', 'editor', 'viewer']:
            raise ValueError(f"Invalid permission level: {permission_level}")
            
        try:
            async with get_db_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO langconnect.assistant_permissions 
                    (assistant_id, user_id, permission_level, granted_by)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (assistant_id, user_id) 
                    DO UPDATE SET
                        permission_level = EXCLUDED.permission_level,
                        granted_by = EXCLUDED.granted_by,
                        updated_at = NOW()
                    """,
                    assistant_id, user_id, permission_level, granted_by
                )
                
                log.info(f"Granted {permission_level} permission on assistant {assistant_id} to {user_id} by {granted_by}")
                return True
                
        except Exception as e:
            log.error(f"Failed to grant assistant permission: {e}")
            return False
    
    @staticmethod
    async def user_can_edit_assistant(user_id: str, assistant_id: str) -> bool:
        """Check if user can edit a specific assistant (owner or editor)."""
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    """
                    SELECT permission_level 
                    FROM langconnect.assistant_permissions 
                    WHERE user_id = $1 AND assistant_id = $2
                    """,
                    user_id, assistant_id
                )
                return result in ['owner', 'editor']
        except Exception as e:
            log.error(f"Failed to check edit permission for assistant {assistant_id}: {e}")
            return False
    
    @staticmethod
    async def user_can_manage_assistant_access(user_id: str, assistant_id: str) -> bool:
        """Check if user can manage access to a specific assistant (owner only)."""
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    """
                    SELECT permission_level 
                    FROM langconnect.assistant_permissions 
                    WHERE user_id = $1 AND assistant_id = $2
                    """,
                    user_id, assistant_id
                )
                return result == 'owner'
        except Exception as e:
            log.error(f"Failed to check management permission for assistant {assistant_id}: {e}")
            return False
    
    @staticmethod
    async def user_can_view_assistant(user_id: str, assistant_id: str) -> bool:
        """Check if user can view/use a specific assistant (any permission level)."""
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    """
                    SELECT permission_level 
                    FROM langconnect.assistant_permissions 
                    WHERE user_id = $1 AND assistant_id = $2
                    """,
                    user_id, assistant_id
                )
                return result in ['owner', 'editor', 'viewer']
        except Exception as e:
            log.error(f"Failed to check view permission for assistant {assistant_id}: {e}")
            return False
    
    @staticmethod
    async def revoke_assistant_permission(assistant_id: str, user_id: str) -> bool:
        """Revoke a user's permission for an assistant.
        
        This is a static method that bypasses ownership checks and is used
        for administrative operations like graph access revocation cleanup.
        
        For default assistants (system-created), we can safely revoke any user's permissions
        since the true "owner" is the system, not individual users.
        
        For user-created assistants, we preserve permissions where the user is the actual owner
        (owner_id in assistant_metadata matches user_id).
        
        Args:
            assistant_id: Assistant identifier
            user_id: User ID to revoke permission from
            
        Returns:
            True if permission was revoked, False otherwise
        """
        try:
            async with get_db_connection() as conn:
                # Determine owner and whether assistant is system-created
                row = await conn.fetchrow(
                    """
                    SELECT 
                        (
                            SELECT user_id
                            FROM langconnect.assistant_permissions p
                            WHERE p.assistant_id = am.assistant_id AND p.permission_level = 'owner'
                            ORDER BY p.created_at ASC
                            LIMIT 1
                        ) AS owner_id,
                        (am.metadata->>'created_by') = 'system' AS is_system
                    FROM langconnect.assistants_mirror am
                    WHERE am.assistant_id = $1::uuid
                    """,
                    assistant_id
                )
                owner_id = row["owner_id"] if row else None
                is_system = bool(row["is_system"]) if row and row["is_system"] is not None else False

                if is_system:
                    result = await conn.execute(
                        """
                        DELETE FROM langconnect.assistant_permissions
                        WHERE assistant_id = $1 AND user_id = $2
                        """,
                        assistant_id, user_id
                    )
                    log.info(f"Revoked permission for user {user_id} on system assistant {assistant_id}")
                else:
                    if owner_id == user_id:
                        log.info(f"Preserving owner permissions for user {user_id} on assistant {assistant_id} (actual owner)")
                        return False
                    result = await conn.execute(
                        """
                        DELETE FROM langconnect.assistant_permissions
                        WHERE assistant_id = $1 AND user_id = $2
                        """,
                        assistant_id, user_id
                    )
                    log.info(f"Revoked permission for user {user_id} on assistant {assistant_id}")
                
                # Extract the number of deleted rows from the result
                if hasattr(result, 'split'):
                    deleted_count = int(result.split()[-1]) if result.split()[-1].isdigit() else 0
                else:
                    deleted_count = 0
                
                if deleted_count > 0:
                    log.info(f"Successfully revoked assistant permission for user {user_id} on assistant {assistant_id}")
                    return True
                else:
                    log.debug(f"No permission found to revoke for user {user_id} on assistant {assistant_id}")
                    return False
                    
        except Exception as e:
            log.error(f"Failed to revoke assistant permission: {e}")
            return False
    
    @staticmethod
    async def update_assistant_metadata(
        assistant_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        """No-op: assistant metadata table removed; updates handled via LangGraph and mirror."""
        return True
    
    @staticmethod
    async def delete_assistant_permissions(assistant_id: str) -> int:
        """Delete all permissions for an assistant."""
        try:
            async with get_db_connection() as conn:
                result = await conn.execute(
                    "DELETE FROM langconnect.assistant_permissions WHERE assistant_id = $1",
                    assistant_id
                )
                deleted_count = int(result.split()[-1]) if result else 0
                log.info(f"Deleted {deleted_count} permissions for assistant {assistant_id}")
                return deleted_count
        except Exception as e:
            log.error(f"Failed to delete assistant permissions for {assistant_id}: {e}")
            return 0
    
    @staticmethod
    async def delete_assistant_metadata(assistant_id: str) -> bool:
        """No-op: assistant metadata table removed."""
        return True