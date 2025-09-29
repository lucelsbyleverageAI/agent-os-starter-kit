from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status

from langconnect.auth import AuthenticatedActor, ServiceAccount, resolve_user_or_service
from langconnect.database import UserRoleManager
 
from langconnect.models import (
    UserRole,
    UserRoleResponse,
    UserRoleUpdate,
    UserListResponse,
    UserRoleAssignment,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserListResponse])
async def users_list(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """List all users with their roles. Only accessible by administrators."""
    try:
        # Get effective user ID for permission checks
        if isinstance(actor, ServiceAccount):
            # Service accounts need admin privileges for user management
            user_manager = UserRoleManager(actor.identity)
            user_manager._is_service_account = True
        else:
            user_manager = UserRoleManager(actor.identity)
        
        users = await user_manager.list_users()
        
        # Convert to response model
        return [UserListResponse(**user) for user in users]
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )


@router.get("/{user_id}", response_model=UserRoleResponse)
async def users_get(
    user_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Get a specific user's role information."""
    try:
        # Get effective user ID for permission checks
        if isinstance(actor, ServiceAccount):
            user_manager = UserRoleManager(actor.identity)
            user_manager._is_service_account = True
        else:
            user_manager = UserRoleManager(actor.identity)
        
        # Users can view their own role, admins can view any role
        can_manage = await user_manager.can_manage_users()
        if not can_manage and user_id != actor.identity:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own user information"
            )
        
        user_role = await user_manager.get_user_role(user_id)
        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        return UserRoleResponse(**user_role)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )


@router.post("", response_model=UserRoleResponse, status_code=status.HTTP_201_CREATED)
async def users_assign_role(
    role_assignment: UserRoleAssignment,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Assign a role to a user. Only accessible by administrators."""
    try:
        # Get effective user ID for permission checks
        if isinstance(actor, ServiceAccount):
            user_manager = UserRoleManager(actor.identity)
            user_manager._is_service_account = True
        else:
            user_manager = UserRoleManager(actor.identity)
        
        # Assign the role
        user_role = await user_manager.assign_role(
            target_user_id=role_assignment.user_id,
            role=role_assignment.role.value,
            email=role_assignment.email,
            display_name=role_assignment.display_name
        )
        
        
        
        return UserRoleResponse(**user_role)
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign user role"
        )


@router.patch("/{user_id}", response_model=UserRoleResponse)
async def users_update_role(
    user_id: str,
    role_update: UserRoleUpdate,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Update a user's role. Only accessible by administrators."""
    try:
        # Get effective user ID for permission checks
        if isinstance(actor, ServiceAccount):
            user_manager = UserRoleManager(actor.identity)
            user_manager._is_service_account = True
        else:
            user_manager = UserRoleManager(actor.identity)
        
        # Update the role
        user_role = await user_manager.update_role(
            target_user_id=user_id,
            new_role=role_update.role.value
        )
        
        
        
        return UserRoleResponse(**user_role)
        
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
            detail="Failed to update user role"
        )


@router.post("/{user_id}/sync", response_model=dict[str, bool])
async def users_sync_info(
    user_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """Sync user email and display_name from auth.users. Only accessible by administrators."""
    try:
        # Get effective user ID for permission checks
        if isinstance(actor, ServiceAccount):
            user_manager = UserRoleManager(actor.identity)
            user_manager._is_service_account = True
        else:
            user_manager = UserRoleManager(actor.identity)
        
        # Check permissions
        if not await user_manager.can_manage_users():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can sync user information"
            )
        
        # Sync user information
        success = await user_manager.sync_user_info(user_id)
        
        
        
        return {"success": success}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync user information"
        ) 