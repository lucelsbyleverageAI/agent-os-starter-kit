from typing import List, Optional, Dict, Any
import logging

from langconnect.database.connection import get_db_connection
from langconnect.database.user_roles import UserRoleManager
from langconnect.database.graph_permissions import GraphPermissionManager

# Standard Python logger for general logging
log = logging.getLogger(__name__)


class AssistantPermissionManager:
    """Manager for assistant permission and metadata operations."""
    
    def __init__(self, user_id: str):
        """Initialize AssistantPermissionManager.
        
        Args:
            user_id: The ID of the user performing the operations
        """
        self.user_id = user_id
        self.user_role_manager = UserRoleManager(user_id)
        self.graph_permission_manager = GraphPermissionManager(user_id)
        self._is_service_account = False
    
    def _sync_service_account_flag(self):
        """Sync the service account flag to the dependent managers."""
        self.user_role_manager._is_service_account = self._is_service_account
        self.graph_permission_manager._is_service_account = self._is_service_account
        self.graph_permission_manager._sync_service_account_flag()
    
    async def register_assistant(
        self,
        assistant_id: str,
        graph_id: str,
        owner_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        share_with: Optional[List[Dict[str, str]]] = None
    ) -> dict:
        """Register a new assistant.
        
        Args:
            assistant_id: LangGraph assistant ID
            graph_id: Base graph ID
            owner_id: Owner user ID
            display_name: User-friendly assistant name
            description: Assistant description
            share_with: List of users to share with upon creation
            
        Returns:
            Assistant metadata information
        """
        # Check if user can create assistants for this graph
        if not await self.user_can_create_assistants(graph_id):
            raise PermissionError("Insufficient permissions to create assistants for this graph")
        
        async with get_db_connection() as connection:
            async with connection.transaction():
                # assistant_metadata table removed; ensure owner permission only
                # Create owner permission
                owner_perm_query = """
                    INSERT INTO langconnect.assistant_permissions 
                    (assistant_id, user_id, permission_level, granted_by)
                    VALUES ($1, $2, 'owner', $3)
                """
                await connection.execute(owner_perm_query, assistant_id, owner_id, self.user_id)
                
                # Share with specified users if provided
                if share_with:
                    for user_perm in share_with:
                        try:
                            share_user_id = user_perm["user_id"]
                            permission_level = user_perm.get("permission_level", "viewer")  # Default to viewer instead of user
                            
                            # Validate permission level - can share with editor or viewer permissions
                            if permission_level not in ["editor", "viewer"]:
                                log.warning(f"Invalid permission level {permission_level} for user {share_user_id}, defaulting to 'viewer'")
                                permission_level = "viewer"
                            
                            share_query = """
                                INSERT INTO langconnect.assistant_permissions 
                                (assistant_id, user_id, permission_level, granted_by)
                                VALUES ($1, $2, $3, $4)
                                ON CONFLICT (assistant_id, user_id) DO NOTHING
                            """
                            await connection.execute(share_query, assistant_id, share_user_id, permission_level, self.user_id)
                            
                        except Exception as e:
                            log.error(f"Error sharing assistant with {user_perm.get('user_id', 'unknown')}: {e}")
                
                # Attach graph_id from assistants_mirror
                graph_row = await connection.fetchrow(
                    "SELECT graph_id FROM langconnect.assistants_mirror WHERE assistant_id = $1::uuid",
                    assistant_id
                )
                return {
                    "assistant_id": assistant_id,
                    "owner_id": owner_id,
                    "display_name": display_name,
                    "description": description,
                    "created_at": None,
                    "updated_at": None,
                    "graph_id": graph_row["graph_id"] if graph_row else graph_id,
                }
    
    async def get_assistant_metadata(self, assistant_id: str) -> Optional[dict]:
        """Get assistant metadata.
        
        Args:
            assistant_id: Assistant identifier
            
        Returns:
            Assistant metadata or None if not found
        """
        # Check if user can access this assistant
        if not await self.user_can_access_assistant(assistant_id):
            raise PermissionError("Insufficient permissions to access this assistant")
        
        async with get_db_connection() as connection:
            query = """
                SELECT 
                    am.assistant_id::text as assistant_id,
                    am.graph_id,
                    owner_perm.user_id as owner_id,
                    ur.email as owner_email,
                    ur.display_name as owner_display_name,
                    am.name as display_name,
                    am.description,
                    am.langgraph_created_at as created_at,
                    am.langgraph_updated_at as updated_at
                FROM langconnect.assistants_mirror am
                LEFT JOIN LATERAL (
                    SELECT user_id
                    FROM langconnect.assistant_permissions p
                    WHERE p.assistant_id = am.assistant_id AND p.permission_level = 'owner'
                    ORDER BY p.created_at ASC
                    LIMIT 1
                ) AS owner_perm ON TRUE
                LEFT JOIN langconnect.user_roles ur ON owner_perm.user_id = ur.user_id
                WHERE am.assistant_id = $1::uuid
            """
            result = await connection.fetchrow(query, assistant_id)
            
            return dict(result) if result else None
    
    async def get_accessible_assistants(self) -> List[dict]:
        """Get all assistants the current user has access to.
        
        Returns:
            List of accessible assistants with metadata
        """
        async with get_db_connection() as connection:
            query = """
                SELECT 
                    ap.assistant_id,
                    am.graph_id,
                    am.name AS display_name,
                    am.description,
                    ap.permission_level,
                    owner_perm.user_id AS owner_id,
                    ur.email AS owner_email,
                    ur.display_name AS owner_display_name,
                    am.langgraph_created_at AS created_at,
                    COUNT(ap2.user_id) - 1 as shared_with_count
                FROM langconnect.assistant_permissions ap
                JOIN langconnect.assistants_mirror am ON ap.assistant_id::uuid = am.assistant_id
                LEFT JOIN LATERAL (
                    SELECT user_id
                    FROM langconnect.assistant_permissions p
                    WHERE p.assistant_id = am.assistant_id AND p.permission_level = 'owner'
                    ORDER BY p.created_at ASC
                    LIMIT 1
                ) AS owner_perm ON TRUE
                LEFT JOIN langconnect.user_roles ur ON owner_perm.user_id = ur.user_id
                LEFT JOIN langconnect.assistant_permissions ap2 ON ap.assistant_id = ap2.assistant_id
                WHERE ap.user_id = $1
                GROUP BY ap.assistant_id, am.graph_id, am.name, am.description, 
                         ap.permission_level, owner_perm.user_id, ur.email, ur.display_name, am.langgraph_created_at
                ORDER BY am.langgraph_created_at DESC NULLS LAST
            """
            results = await connection.fetch(query, self.user_id)
            
            return [dict(result) for result in results]
    
    async def get_assistant_permissions(self, assistant_id: str) -> List[dict]:
        """Get all permissions for a specific assistant.
        
        Args:
            assistant_id: Assistant identifier
            
        Returns:
            List of permission information for the assistant
        """
        # Check if user can manage this assistant
        if not await self.user_can_manage_assistant(assistant_id):
            raise PermissionError("Insufficient permissions to view assistant permissions")
        
        async with get_db_connection() as connection:
            query = """
                SELECT 
                    ap.id,
                    ap.assistant_id,
                    ap.user_id,
                    ur.email,
                    ur.display_name,
                    ap.permission_level,
                    ap.granted_by,
                    ap.created_at,
                    ap.updated_at
                FROM langconnect.assistant_permissions ap
                LEFT JOIN langconnect.user_roles ur ON ap.user_id = ur.user_id
                WHERE ap.assistant_id = $1
                ORDER BY ap.permission_level DESC, ap.created_at ASC
            """
            results = await connection.fetch(query, assistant_id)
            
            return [dict(result) for result in results]
    
    async def share_assistant(
        self, 
        assistant_id: str, 
        users_permissions: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Share an assistant with users.
        
        Args:
            assistant_id: Assistant identifier
            users_permissions: List of dicts with user_id and permission_level
            
        Returns:
            Dict with success/error information
        """
        # Check if user can manage this assistant
        if not await self.user_can_manage_assistant(assistant_id):
            raise PermissionError("Insufficient permissions to share this assistant")
        
        successful_shares = []
        errors = []
        
        async with get_db_connection() as connection:
            for user_perm in users_permissions:
                try:
                    user_id = user_perm["user_id"]
                    permission_level = user_perm.get("permission_level", "viewer")  # Default to viewer instead of user
                    
                    # Validate permission level - can share with editor or viewer permissions
                    if permission_level not in ["editor", "viewer"]:
                        log.warning(f"Invalid permission level {permission_level} for user {user_id}, defaulting to 'viewer'")
                        permission_level = "viewer"
                    
                    # Insert or update permission
                    query = """
                        INSERT INTO langconnect.assistant_permissions (assistant_id, user_id, permission_level, granted_by)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (assistant_id, user_id) DO UPDATE SET
                            permission_level = EXCLUDED.permission_level,
                            granted_by = EXCLUDED.granted_by,
                            updated_at = NOW()
                        RETURNING id, assistant_id, user_id, permission_level, created_at
                    """
                    result = await connection.fetchrow(
                        query, assistant_id, user_id, permission_level, self.user_id
                    )
                    
                    if result:
                        successful_shares.append({
                            "user_id": user_id,
                            "permission_level": permission_level,
                            "id": str(result["id"])
                        })
                    else:
                        errors.append({
                            "user_id": user_id,
                            "error": "Failed to share assistant"
                        })
                        
                except Exception as e:
                    log.error(f"Error sharing assistant with {user_perm.get('user_id', 'unknown')}: {e}")
                    errors.append({
                        "user_id": user_perm.get("user_id", "unknown"),
                        "error": str(e)
                    })
        
        return {
            "assistant_id": assistant_id,
            "shared_with": successful_shares,
            "errors": errors
        }
    
    async def revoke_assistant_permission(self, assistant_id: str, target_user_id: str) -> bool:
        """Revoke a user's permission for an assistant.
        
        Args:
            assistant_id: Assistant identifier
            target_user_id: User ID to revoke permission from
            
        Returns:
            True if permission was revoked, False otherwise
        """
        # Check if user can manage this assistant
        if not await self.user_can_manage_assistant(assistant_id):
            raise PermissionError("Insufficient permissions to manage this assistant")
        
        # Don't allow revoking owner permissions (there must always be at least one owner)
        async with get_db_connection() as connection:
            # Check if target user is an owner
            owner_check_query = """
                SELECT permission_level
                FROM langconnect.assistant_permissions
                WHERE assistant_id = $1 AND user_id = $2
            """
            target_permission = await connection.fetchrow(owner_check_query, assistant_id, target_user_id)
            
            if target_permission and target_permission["permission_level"] == "owner":
                # Count total owners
                owner_count_query = """
                    SELECT COUNT(*)
                    FROM langconnect.assistant_permissions
                    WHERE assistant_id = $1 AND permission_level = 'owner'
                """
                owner_count = await connection.fetchval(owner_count_query, assistant_id)
                
                if owner_count <= 1:
                    raise ValueError("Cannot revoke the last owner's permission. Transfer ownership first.")
            
            # Revoke permission
            revoke_query = """
                DELETE FROM langconnect.assistant_permissions
                WHERE assistant_id = $1 AND user_id = $2 AND permission_level != 'owner'
            """
            result = await connection.execute(revoke_query, assistant_id, target_user_id)
            
            # Extract the number of deleted rows from the result
            if hasattr(result, 'split'):
                deleted_count = int(result.split()[-1]) if result.split()[-1].isdigit() else 0
            else:
                deleted_count = 0
            
            return deleted_count > 0
    
    async def user_can_access_assistant(self, assistant_id: str) -> bool:
        """Check if user can access a specific assistant.
        
        Args:
            assistant_id: Assistant identifier
            
        Returns:
            True if user can access the assistant, False otherwise
        """
        async with get_db_connection() as connection:
            query = """
                SELECT 1
                FROM langconnect.assistant_permissions
                WHERE assistant_id = $1 AND user_id = $2
            """
            result = await connection.fetchrow(query, assistant_id, self.user_id)
            
            return result is not None
    
    async def user_can_manage_assistant(self, assistant_id: str) -> bool:
        """Check if user can manage a specific assistant.
        
        Args:
            assistant_id: Assistant identifier
            
        Returns:
            True if user can manage the assistant (is owner), False otherwise
        """
        async with get_db_connection() as connection:
            query = """
                SELECT permission_level
                FROM langconnect.assistant_permissions
                WHERE assistant_id = $1 AND user_id = $2
            """
            result = await connection.fetchrow(query, assistant_id, self.user_id)
            
            return result and result["permission_level"] == "owner"
    
    async def user_can_create_assistants(self, graph_id: str) -> bool:
        """Check if user can create assistants for a specific graph.
        
        Args:
            graph_id: Graph identifier
            
        Returns:
            True if user can create assistants for the graph, False otherwise
        """
        # User needs access to the graph to create assistants
        return await self.graph_permission_manager.user_can_access_graph(graph_id)
    
    async def get_user_assistant_permission(self, assistant_id: str) -> Optional[str]:
        """Get the current user's permission level for a specific assistant.
        
        Args:
            assistant_id: Assistant identifier
            
        Returns:
            Permission level string or None if no access
        """
        async with get_db_connection() as connection:
            query = """
                SELECT permission_level
                FROM langconnect.assistant_permissions
                WHERE assistant_id = $1 AND user_id = $2
            """
            result = await connection.fetchrow(query, assistant_id, self.user_id)
            
            return result["permission_level"] if result else None

    @staticmethod
    async def get_public_assistants() -> List[Dict[str, Any]]:
        """Get all active public assistants from the database.
        
        Returns:
            List of public assistants with their assistant_id and permission_level.
        """
        async with get_db_connection() as connection:
            query = """
                SELECT assistant_id, permission_level
                FROM langconnect.public_assistant_permissions
                WHERE revoked_at IS NULL
            """
            results = await connection.fetch(query)
            return [dict(row) for row in results]

    @staticmethod
    async def get_all_public_assistant_permissions() -> List[Dict[str, Any]]:
        """Get all public assistant permissions, including revoked ones."""
        async with get_db_connection() as connection:
            query = """
                SELECT 
                    pap.id,
                    pap.assistant_id,
                    pap.permission_level,
                    pap.created_at,
                    pap.revoked_at,
                    pap.revoke_mode,
                    pap.notes,
                    ur.email AS created_by_email,
                    ur.display_name AS created_by_display_name
                FROM langconnect.public_assistant_permissions pap
                LEFT JOIN langconnect.user_roles ur ON pap.created_by::text = ur.user_id
                ORDER BY pap.created_at DESC
            """
            results = await connection.fetch(query)
            return [dict(row) for row in results]

    @staticmethod
    async def get_all_assistant_permissions_for_user(user_id: str) -> List[str]:
        """Get all assistant IDs a specific user has permissions for.
        
        Args:
            user_id: The ID of the user to check.
            
        Returns:
            A list of assistant_ids the user can access.
        """
        async with get_db_connection() as connection:
            query = "SELECT assistant_id FROM langconnect.assistant_permissions WHERE user_id = $1"
            results = await connection.fetch(query, user_id)
            return [row['assistant_id'] for row in results]

    @staticmethod
    async def revoke_public_assistant_permission(assistant_id: str, mode: str) -> Dict[str, Any]:
        """Revoke a public permission for an assistant.

        Args:
            assistant_id: The ID of the assistant.
            mode: The revocation mode ('revoke_all' or 'future_only').

        Returns:
            A dictionary with a summary of the revocation.
        """
        if mode not in ['revoke_all', 'future_only']:
            raise ValueError("Invalid revocation mode. Must be 'revoke_all' or 'future_only'.")

        async with get_db_connection() as connection:
            async with connection.transaction():
                update_query = """
                    UPDATE langconnect.public_assistant_permissions
                    SET revoked_at = NOW(), revoke_mode = $1
                    WHERE assistant_id = $2 AND revoked_at IS NULL
                    RETURNING id
                """
                result = await connection.fetchrow(update_query, mode, assistant_id)

                if not result:
                    raise ValueError(f"No active public permission found for assistant_id: {assistant_id}")

                revoked_count = 0
                if mode == 'revoke_all':
                    delete_query = """
                        DELETE FROM langconnect.assistant_permissions
                        WHERE assistant_id = $1 AND granted_by = 'system:public'
                    """
                    delete_result = await connection.execute(delete_query, assistant_id)
                    if hasattr(delete_result, 'split'):
                        revoked_count = int(delete_result.split()[-1]) if delete_result.split()[-1].isdigit() else 0
                    else:
                        revoked_count = 0
                
                return {
                    "assistant_id": assistant_id,
                    "status": "revoked",
                    "mode": mode,
                    "revoked_user_count": revoked_count
                }

    @staticmethod
    async def grant_permission_as_system(user_id: str, assistant_id: str, permission_level: str) -> bool:
        """Grant an assistant permission to a user on behalf of the system.
        
        Args:
            user_id: The ID of the user receiving the permission.
            assistant_id: The ID of the assistant.
            permission_level: The permission level to grant ('viewer', 'editor', etc.).
            
        Returns:
            True if the permission was granted, False otherwise.
        """
        async with get_db_connection() as connection:
            query = """
                INSERT INTO langconnect.assistant_permissions (assistant_id, user_id, permission_level, granted_by)
                VALUES ($1, $2, $3, 'system:public')
                ON CONFLICT (assistant_id, user_id) DO NOTHING
            """
            result = await connection.execute(query, assistant_id, user_id, permission_level)
            return "INSERT 0 1" in result 