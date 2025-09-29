from typing import List, Optional, Dict, Any
import logging

from langconnect.database.connection import get_db_connection
from langconnect.database.user_roles import UserRoleManager

# Standard Python logger for general logging
log = logging.getLogger(__name__)


class GraphPermissionManager:
    """Manager for graph permission operations."""
    
    @staticmethod
    async def get_public_graphs() -> List[Dict[str, Any]]:
        """Get all active public graphs from the database.
        
        Returns:
            List of public graphs with their graph_id and permission_level.
        """
        async with get_db_connection() as connection:
            query = """
                SELECT graph_id, permission_level
                FROM langconnect.public_graph_permissions
                WHERE revoked_at IS NULL
            """
            results = await connection.fetch(query)
            return [dict(row) for row in results]

    @staticmethod
    async def get_all_public_graph_permissions() -> List[Dict[str, Any]]:
        """Get all public graph permissions, including revoked ones."""
        async with get_db_connection() as connection:
            query = """
                SELECT 
                    pgp.id,
                    pgp.graph_id,
                    pgp.permission_level,
                    pgp.created_at,
                    pgp.revoked_at,
                    pgp.revoke_mode,
                    pgp.notes,
                    ur.email AS created_by_email,
                    ur.display_name AS created_by_display_name
                FROM langconnect.public_graph_permissions pgp
                LEFT JOIN langconnect.user_roles ur ON pgp.created_by::text = ur.user_id
                ORDER BY pgp.created_at DESC
            """
            results = await connection.fetch(query)
            return [dict(row) for row in results]

    @staticmethod
    async def get_all_graph_permissions_for_user(user_id: str) -> List[str]:
        """Get all graph IDs a specific user has permissions for.
        
        Args:
            user_id: The ID of the user to check.
            
        Returns:
            A list of graph_ids the user can access.
        """
        async with get_db_connection() as connection:
            query = "SELECT graph_id FROM langconnect.graph_permissions WHERE user_id = $1"
            results = await connection.fetch(query, user_id)
            return [row['graph_id'] for row in results]

    @staticmethod
    async def grant_permission_as_system(user_id: str, graph_id: str, permission_level: str) -> bool:
        """Grant a graph permission to a user on behalf of the system.
        
        This is used for materializing public permissions and bypasses normal
        user-based permission checks.
        
        Args:
            user_id: The ID of the user receiving the permission.
            graph_id: The ID of the graph.
            permission_level: The permission level to grant ('access' or 'admin').
            
        Returns:
            True if the permission was granted, False otherwise.
        """
        async with get_db_connection() as connection:
            query = """
                INSERT INTO langconnect.graph_permissions (graph_id, user_id, permission_level, granted_by)
                VALUES ($1, $2, $3, 'system:public')
                ON CONFLICT (graph_id, user_id) DO NOTHING
            """
            result = await connection.execute(query, graph_id, user_id, permission_level)
            return "INSERT 0 1" in result

    def __init__(self, user_id: str):
        """Initialize GraphPermissionManager.
        
        Args:
            user_id: The ID of the user performing the operations
        """
        self.user_id = user_id
        self.user_role_manager = UserRoleManager(user_id)
        self._is_service_account = False
    
    def _sync_service_account_flag(self):
        """Sync the service account flag to the user role manager."""
        self.user_role_manager._is_service_account = self._is_service_account
    
    async def get_accessible_graphs(self) -> List[str]:
        """Get list of graphs the current user has access to.
        
        Returns:
            List of graph IDs the user can access
        """
        # Dev admins have access to all graphs (no explicit permissions needed)
        if await self.user_role_manager.is_dev_admin():
            # Return empty list here - the API layer will handle dev_admin special access
            # This allows dev_admins to access any graph without explicit permissions
            return []
        
        async with get_db_connection() as connection:
            query = """
                SELECT DISTINCT graph_id
                FROM langconnect.graph_permissions
                WHERE user_id = $1
                ORDER BY graph_id
            """
            results = await connection.fetch(query, self.user_id)
            
            return [result["graph_id"] for result in results]
    
    async def get_graph_permissions(self, graph_id: str) -> List[dict]:
        """Get all permissions for a specific graph.
        
        Args:
            graph_id: Graph identifier to get permissions for
            
        Returns:
            List of permission information for the graph
        """
        # Check if user can view permissions for this graph
        if not await self.user_can_admin_graph(graph_id):
            raise PermissionError("Insufficient permissions to view graph permissions")
        
        async with get_db_connection() as connection:
            query = """
                SELECT 
                    gp.id,
                    gp.graph_id,
                    gp.user_id,
                    ur.email,
                    ur.display_name,
                    gp.permission_level,
                    gp.granted_by,
                    gp.created_at,
                    gp.updated_at
                FROM langconnect.graph_permissions gp
                LEFT JOIN langconnect.user_roles ur ON gp.user_id = ur.user_id
                WHERE gp.graph_id = $1
                ORDER BY gp.created_at ASC
            """
            results = await connection.fetch(query, graph_id)
            
            return [dict(result) for result in results]
    
    async def grant_graph_permissions(
        self, 
        graph_id: str, 
        users_permissions: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Grant permissions to users for a graph.
        
        Args:
            graph_id: Graph identifier to grant permissions for
            users_permissions: List of dicts with user_id and permission_level
            
        Returns:
            Dict with success/error information
        """
        # Check if user can manage permissions for this graph
        if not await self.user_can_admin_graph(graph_id):
            raise PermissionError("Insufficient permissions to manage graph permissions")
        
        successful_grants = []
        errors = []
        
        async with get_db_connection() as connection:
            for user_perm in users_permissions:
                try:
                    user_id = user_perm["user_id"]
                    permission_level = user_perm["permission_level"]
                    
                    # Validate permission level
                    if permission_level not in ["admin", "access"]:
                        errors.append({
                            "user_id": user_id,
                            "error": f"Invalid permission level: {permission_level}"
                        })
                        continue
                    
                    # Insert or update permission
                    query = """
                        INSERT INTO langconnect.graph_permissions (graph_id, user_id, permission_level, granted_by)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (graph_id, user_id) DO UPDATE SET
                            permission_level = EXCLUDED.permission_level,
                            granted_by = EXCLUDED.granted_by,
                            updated_at = NOW()
                        RETURNING id, graph_id, user_id, permission_level, created_at
                    """
                    result = await connection.fetchrow(
                        query, graph_id, user_id, permission_level, self.user_id
                    )
                    
                    if result:
                        successful_grants.append({
                            "user_id": user_id,
                            "permission_level": permission_level,
                            "id": str(result["id"])
                        })
                    else:
                        errors.append({
                            "user_id": user_id,
                            "error": "Failed to grant permission"
                        })
                        
                except Exception as e:
                    log.error(f"Error granting permission to {user_perm.get('user_id', 'unknown')}: {e}")
                    errors.append({
                        "user_id": user_perm.get("user_id", "unknown"),
                        "error": str(e)
                    })
        
        return {
            "graph_id": graph_id,
            "successful_grants": successful_grants,
            "errors": errors
        }
    
    async def revoke_graph_permission(self, graph_id: str, target_user_id: str) -> bool:
        """Revoke a user's permission for a graph.
        
        Args:
            graph_id: Graph identifier
            target_user_id: User ID to revoke permission from
            
        Returns:
            True if permission was revoked, False otherwise
        """
        # Check if user can manage permissions for this graph
        if not await self.user_can_admin_graph(graph_id):
            raise PermissionError("Insufficient permissions to manage graph permissions")
        
        async with get_db_connection() as connection:
            query = """
                DELETE FROM langconnect.graph_permissions
                WHERE graph_id = $1 AND user_id = $2
            """
            result = await connection.execute(query, graph_id, target_user_id)
            
            # Extract the number of deleted rows from the result
            if hasattr(result, 'split'):
                # PostgreSQL returns "DELETE n" where n is the number of rows
                deleted_count = int(result.split()[-1]) if result.split()[-1].isdigit() else 0
            else:
                deleted_count = 0
            
            return deleted_count > 0
    
    async def user_can_access_graph(self, graph_id: str) -> bool:
        """Check if user can access a specific graph.
        
        Args:
            graph_id: Graph identifier to check access for
            
        Returns:
            True if user can access the graph, False otherwise
        """
        # Dev admins can access all graphs
        if await self.user_role_manager.is_dev_admin():
            return True
        
        async with get_db_connection() as connection:
            query = """
                SELECT 1
                FROM langconnect.graph_permissions
                WHERE graph_id = $1 AND user_id = $2
            """
            result = await connection.fetchrow(query, graph_id, self.user_id)
            
            return result is not None
    
    async def user_can_admin_graph(self, graph_id: str) -> bool:
        """Check if user can manage permissions for a specific graph.
        
        Args:
            graph_id: Graph identifier to check admin access for
            
        Returns:
            True if user can manage graph permissions, False otherwise
        """
        # Dev admins can manage all graph permissions
        if await self.user_role_manager.is_dev_admin():
            return True
        
        async with get_db_connection() as connection:
            query = """
                SELECT permission_level
                FROM langconnect.graph_permissions
                WHERE graph_id = $1 AND user_id = $2
            """
            result = await connection.fetchrow(query, graph_id, self.user_id)
            
            return result and result["permission_level"] == "admin"
    
    async def get_user_graph_permission(self, graph_id: str) -> Optional[str]:
        """Get the current user's permission level for a specific graph.
        
        Args:
            graph_id: Graph identifier to check
            
        Returns:
            Permission level string or None if no access
        """
        # Dev admins have implicit admin access to all graphs
        if await self.user_role_manager.is_dev_admin():
            return "admin"
        
        async with get_db_connection() as connection:
            query = """
                SELECT permission_level
                FROM langconnect.graph_permissions
                WHERE graph_id = $1 AND user_id = $2
            """
            result = await connection.fetchrow(query, graph_id, self.user_id)
            
            return result["permission_level"] if result else None
    
    async def get_graph_user_count(self, graph_id: str) -> int:
        """Get the number of users with access to a specific graph.
        
        Args:
            graph_id: Graph identifier
            
        Returns:
            Number of users with access to the graph
        """
        async with get_db_connection() as connection:
            query = """
                SELECT COUNT(DISTINCT user_id)
                FROM langconnect.graph_permissions
                WHERE graph_id = $1
            """
            result = await connection.fetchval(query, graph_id)
            
            return result or 0
    
    async def list_graphs_with_access_info(self) -> List[Dict[str, Any]]:
        """List all graphs with access information for the current user.
        
        Returns:
            List of graphs with access information
        """
        # For dev_admins, we would need to get this info from LangGraph
        # This method is mainly for regular users to see their accessible graphs
        if await self.user_role_manager.is_dev_admin():
            # Dev admins see all graphs - this would be handled at the API layer
            return []
        
        async with get_db_connection() as connection:
            query = """
                SELECT 
                    gp.graph_id,
                    gp.permission_level,
                    COUNT(DISTINCT gp2.user_id) as user_count
                FROM langconnect.graph_permissions gp
                LEFT JOIN langconnect.graph_permissions gp2 ON gp.graph_id = gp2.graph_id
                WHERE gp.user_id = $1
                GROUP BY gp.graph_id, gp.permission_level
                ORDER BY gp.graph_id
            """
            results = await connection.fetch(query, self.user_id)
            
            return [
                {
                    "graph_id": result["graph_id"],
                    "permission_level": result["permission_level"],
                    "user_count": result["user_count"] or 0
                }
                for result in results
            ]

    @staticmethod
    async def revoke_public_graph_permission(graph_id: str, mode: str) -> Dict[str, Any]:
        """Revoke a public permission for a graph and all its related assistants.

        Args:
            graph_id: The ID of the graph.
            mode: The revocation mode ('revoke_all' or 'future_only').

        Returns:
            A dictionary with a summary of the revocation.
        """
        if mode not in ['revoke_all', 'future_only']:
            raise ValueError("Invalid revocation mode. Must be 'revoke_all' or 'future_only'.")

        async with get_db_connection() as connection:
            async with connection.transaction():
                # Step 1: Revoke the public graph permission
                update_query = """
                    UPDATE langconnect.public_graph_permissions
                    SET revoked_at = NOW(), revoke_mode = $1
                    WHERE graph_id = $2 AND revoked_at IS NULL
                    RETURNING id
                """
                result = await connection.fetchrow(update_query, mode, graph_id)

                if not result:
                    raise ValueError(f"No active public permission found for graph_id: {graph_id}")

                # Step 2: Find all assistants belonging to this graph (use mirror)
                assistant_query = """
                    SELECT assistant_id 
                    FROM langconnect.assistants_mirror 
                    WHERE graph_id = $1
                """
                assistant_results = await connection.fetch(assistant_query, graph_id)
                assistant_ids = [row['assistant_id'] for row in assistant_results]

                # Step 3: Revoke public assistant permissions for all related assistants
                assistant_permissions_revoked = 0
                for assistant_id in assistant_ids:
                    assistant_id_text = str(assistant_id)
                    # Check if the assistant has an active public permission
                    assistant_public_check = await connection.fetchrow(
                        "SELECT id FROM langconnect.public_assistant_permissions WHERE assistant_id = $1 AND revoked_at IS NULL",
                        assistant_id_text
                    )
                    
                    if assistant_public_check:
                        # Revoke the public assistant permission
                        await connection.execute(
                            """
                            UPDATE langconnect.public_assistant_permissions
                            SET revoked_at = NOW(), revoke_mode = $1
                            WHERE assistant_id = $2 AND revoked_at IS NULL
                            """,
                            mode, assistant_id_text
                        )
                        assistant_permissions_revoked += 1

                # Step 4: Remove materialized permissions if mode is 'revoke_all'
                revoked_graph_permissions = 0
                revoked_assistant_permissions = 0
                
                if mode == 'revoke_all':
                    # Remove materialized graph permissions
                    graph_delete_query = """
                        DELETE FROM langconnect.graph_permissions
                        WHERE graph_id = $1 AND granted_by = 'system:public'
                    """
                    graph_delete_result = await connection.execute(graph_delete_query, graph_id)
                    if hasattr(graph_delete_result, 'split'):
                        revoked_graph_permissions = int(graph_delete_result.split()[-1]) if graph_delete_result.split()[-1].isdigit() else 0

                    # Remove materialized assistant permissions for related assistants
                    if assistant_ids:
                        assistant_delete_query = """
                            DELETE FROM langconnect.assistant_permissions
                            WHERE assistant_id = ANY($1::uuid[]) AND granted_by = 'system:public'
                        """
                        assistant_delete_result = await connection.execute(assistant_delete_query, [str(a) for a in assistant_ids])
                        if hasattr(assistant_delete_result, 'split'):
                            revoked_assistant_permissions = int(assistant_delete_result.split()[-1]) if assistant_delete_result.split()[-1].isdigit() else 0

                return {
                    "graph_id": graph_id,
                    "status": "revoked",
                    "mode": mode,
                    "revoked_graph_permissions": revoked_graph_permissions,
                    "revoked_assistant_permissions": revoked_assistant_permissions,
                    "related_assistants_count": len(assistant_ids),
                    "assistant_public_permissions_revoked": assistant_permissions_revoked
                } 