from typing import List, Optional
import logging

from langconnect.database.connection import get_db_connection

# Standard Python logger for general logging
log = logging.getLogger(__name__)


class UserRoleManager:
    """Manager for user role operations."""
    
    def __init__(self, user_id: str):
        """Initialize UserRoleManager.
        
        Args:
            user_id: The ID of the user performing the operations
        """
        self.user_id = user_id
        self._is_service_account = False
    
    async def get_user_role(self, target_user_id: Optional[str] = None) -> dict | None:
        """Get a user's role information.
        
        Args:
            target_user_id: User ID to get role for. If None, gets current user's role.
            
        Returns:
            User role information or None if not found
        """
        user_to_check = target_user_id if target_user_id else self.user_id
        
        async with get_db_connection() as connection:
            query = """
                SELECT id, user_id, email, display_name, role, assigned_by, created_at, updated_at
                FROM langconnect.user_roles
                WHERE user_id = $1
            """
            result = await connection.fetchrow(query, user_to_check)
            
            if result:
                return dict(result)
            return None
    
    async def list_users(self) -> List[dict]:
        """List all users with their roles.
        
        Returns:
            List of user role information
        """
        # Service accounts have admin access
        if not self._is_service_account and not await self.can_manage_users():
            raise PermissionError("Only administrators can list all users")
        
        async with get_db_connection() as connection:
            query = """
                SELECT id, user_id, email, display_name, role, created_at
                FROM langconnect.user_roles
                ORDER BY created_at ASC
            """
            results = await connection.fetch(query)
            
            return [dict(result) for result in results]
    
    async def assign_role(
        self, 
        target_user_id: str, 
        role: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None
    ) -> dict:
        """Assign a role to a user.
        
        Args:
            target_user_id: User ID to assign role to
            role: Role to assign (dev_admin, business_admin, user)
            email: User email (will be synced from auth.users if not provided)
            display_name: User display name (will be synced from auth.users if not provided)
            
        Returns:
            User role information after assignment
        """
        # Service accounts have admin access
        if not self._is_service_account and not await self.can_manage_users():
            raise PermissionError("Only administrators can assign user roles")
        
        async with get_db_connection() as connection:
            # If email/display_name not provided, sync from auth.users
            if not email or not display_name:
                sync_query = "SELECT langconnect.sync_user_role_info($1)"
                await connection.fetchval(sync_query, target_user_id)
            
            # Insert or update user role
            query = """
                INSERT INTO langconnect.user_roles (user_id, role, assigned_by, email, display_name)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO UPDATE SET
                    role = EXCLUDED.role,
                    assigned_by = EXCLUDED.assigned_by,
                    email = COALESCE(EXCLUDED.email, langconnect.user_roles.email),
                    display_name = COALESCE(EXCLUDED.display_name, langconnect.user_roles.display_name),
                    updated_at = NOW()
                RETURNING id, user_id, email, display_name, role, assigned_by, created_at, updated_at
            """
            result = await connection.fetchrow(
                query, target_user_id, role, self.user_id, email, display_name
            )
            
            if result:
                return dict(result)
            
            raise RuntimeError("Failed to assign user role")
    
    async def update_role(self, target_user_id: str, new_role: str) -> dict:
        """Update an existing user's role.
        
        Args:
            target_user_id: User ID to update role for
            new_role: New role to assign
            
        Returns:
            Updated user role information
        """
        # Service accounts have admin access
        if not self._is_service_account and not await self.can_manage_users():
            raise PermissionError("Only administrators can update user roles")
        
        async with get_db_connection() as connection:
            query = """
                UPDATE langconnect.user_roles
                SET role = $1, assigned_by = $2, updated_at = NOW()
                WHERE user_id = $3
                RETURNING id, user_id, email, display_name, role, assigned_by, created_at, updated_at
            """
            result = await connection.fetchrow(query, new_role, self.user_id, target_user_id)
            
            if result:
                return dict(result)
            
            raise ValueError(f"User {target_user_id} not found or role update failed")
    
    async def is_dev_admin(self) -> bool:
        """Check if current user is a dev_admin.
        
        Returns:
            True if user is dev_admin, False otherwise
        """
        # Service accounts have dev_admin privileges
        if self._is_service_account:
            return True
            
        user_role = await self.get_user_role()
        return user_role and user_role.get("role") == "dev_admin"
    
    async def is_business_admin(self) -> bool:
        """Check if current user is a business_admin.
        
        Returns:
            True if user is business_admin, False otherwise
        """
        # Service accounts have business_admin privileges
        if self._is_service_account:
            return True
            
        user_role = await self.get_user_role()
        return user_role and user_role.get("role") == "business_admin"
    
    async def can_manage_users(self) -> bool:
        """Check if current user can manage other users.
        
        Returns:
            True if user can manage users (dev_admin or business_admin), False otherwise
        """
        # Service accounts have admin access
        if self._is_service_account:
            return True
            
        user_role = await self.get_user_role()
        if not user_role:
            return False
        
        role = user_role.get("role")
        return role in ["dev_admin", "business_admin"]
    
    async def can_manage_graph_permissions(self) -> bool:
        """Check if current user can manage graph permissions.
        
        Returns:
            True if user can manage graph permissions (dev_admin), False otherwise
        """
        # Service accounts have dev_admin privileges
        if self._is_service_account:
            return True
            
        return await self.is_dev_admin()
    
    async def get_role_string(self) -> Optional[str]:
        """Get the current user's role as a string.
        
        Returns:
            Role string or None if user has no role
        """
        # Service accounts are treated as dev_admin
        if self._is_service_account:
            return "dev_admin"
            
        user_role = await self.get_user_role()
        return user_role.get("role") if user_role else None
    
    async def sync_user_info(self, target_user_id: str) -> bool:
        """Sync user email and display_name from auth.users.
        
        Args:
            target_user_id: User ID to sync info for
            
        Returns:
            True if sync was successful, False otherwise
        """
        try:
            async with get_db_connection() as connection:
                query = "SELECT langconnect.sync_user_role_info($1)"
                await connection.fetchval(query, target_user_id)
                return True
        except Exception as e:
            log.error(f"Failed to sync user info for {target_user_id}: {e}")
            return False 