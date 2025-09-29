import datetime
from typing import Any, List
from enum import Enum

from pydantic import BaseModel, Field

# =====================
# Enum for Permission Levels
# =====================


class PermissionLevel(str, Enum):
    """Enum for collection permission levels."""
    
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


# =====================
# Collection Schemas
# =====================


class CollectionCreate(BaseModel):
    """Schema for creating a new collection."""

    name: str = Field(..., description="The unique name of the collection.")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata for the collection."
    )
    share_with: List["CollectionPermissionCreate"] | None = Field(
        None, description="Optional list of users to share the collection with upon creation."
    )


class CollectionUpdate(BaseModel):
    """Schema for updating an existing collection."""

    name: str | None = Field(None, description="New name for the collection.")
    metadata: dict[str, Any] | None = Field(
        None, description="Updated metadata for the collection."
    )


class CollectionResponse(BaseModel):
    """Schema for representing a collection from PGVector."""

    # PGVector table has uuid (id), name (str), and cmetadata (JSONB)
    # We get these from list/get db functions
    uuid: str = Field(
        ..., description="The unique identifier of the collection in PGVector."
    )
    name: str = Field(..., description="The name of the collection.")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata associated with the collection."
    )
    permission_level: PermissionLevel | None = Field(
        None, description="User's permission level for this collection."
    )

    class Config:
        # Allows creating model from dict like
        # {'uuid': '...', 'name': '...', 'metadata': {...}}
        from_attributes = True


# =====================
# Permission Schemas
# =====================


class CollectionPermissionCreate(BaseModel):
    """Schema for creating a new collection permission."""
    
    user_id: str = Field(..., description="ID of the user to grant permission to.")
    permission_level: PermissionLevel = Field(..., description="Permission level to grant.")


class CollectionPermissionUpdate(BaseModel):
    """Schema for updating an existing collection permission."""
    
    permission_level: PermissionLevel = Field(..., description="New permission level.")


class CollectionPermissionResponse(BaseModel):
    """Schema for representing a collection permission."""
    
    id: str = Field(..., description="Unique identifier of the permission record.")
    collection_id: str = Field(..., description="ID of the collection.")
    user_id: str = Field(..., description="ID of the user with permission.")
    permission_level: PermissionLevel = Field(..., description="Permission level.")
    granted_by: str = Field(..., description="ID of the user who granted this permission.")
    created_at: datetime.datetime = Field(..., description="When the permission was created.")
    updated_at: datetime.datetime = Field(..., description="When the permission was last updated.")

    class Config:
        from_attributes = True


class CollectionShareRequest(BaseModel):
    """Schema for sharing a collection with multiple users."""
    
    users: List[CollectionPermissionCreate] = Field(
        ..., 
        description="List of users and their permission levels to grant access to."
    )


class CollectionShareResponse(BaseModel):
    """Schema for collection sharing response."""
    
    success: bool = Field(..., description="Whether the sharing operation was successful.")
    shared_with: List[CollectionPermissionResponse] = Field(
        default_factory=list, description="List of permissions that were granted."
    )
    errors: List[str] = Field(
        default_factory=list, description="List of any errors that occurred."
    )


# =====================
# Document Schemas
# =====================


class DocumentBase(BaseModel):
    page_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentCreate(DocumentBase):
    collection_id: str
    embedding: list[float] | None = (
        None  # Embedding can be added during creation or later
    )


class DocumentUpdate(BaseModel):
    page_content: str | None = None
    metadata: dict[str, Any] | None = None
    embedding: list[float] | None = None


class DocumentResponse(DocumentBase):
    id: str
    collection_id: str
    embedding: list[float] | None = None  # Represent embedding as list of floats
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        orm_mode = True
        from_attributes = True  # Pydantic v2 way
