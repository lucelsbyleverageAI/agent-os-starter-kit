from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """User role enumeration for role-based access control."""
    DEV_ADMIN = "dev_admin"
    BUSINESS_ADMIN = "business_admin"
    USER = "user"


class UserRoleResponse(BaseModel):
    """Response model for user role information."""
    id: UUID
    user_id: str
    email: str
    display_name: str
    role: UserRole
    assigned_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class UserRoleUpdate(BaseModel):
    """Request model for updating a user's role."""
    role: UserRole


class UserListResponse(BaseModel):
    """Simplified response model for listing users."""
    id: UUID
    user_id: str
    email: str
    display_name: str
    role: UserRole
    created_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class UserRoleAssignment(BaseModel):
    """Request model for assigning a role to a user."""
    user_id: str = Field(..., description="Supabase user ID")
    role: UserRole
    email: Optional[str] = Field(None, description="User email (will be synced from auth.users if not provided)")
    display_name: Optional[str] = Field(None, description="User display name (will be synced from auth.users if not provided)") 