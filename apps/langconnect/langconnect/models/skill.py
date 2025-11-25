"""
Skill models for the Agent Skills system.

Skills are modular capability packages that extend agent functionality through
filesystem-based instructions, scripts, and resources.
"""

import datetime
import re
from typing import List, Optional, Any
from enum import Enum

from pydantic import BaseModel, Field, field_validator


# =====================
# Enums
# =====================


class SkillPermissionLevel(str, Enum):
    """Enum for skill permission levels."""

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


# =====================
# Skill Schemas
# =====================


# Validation regex for skill names: lowercase, hyphens, numbers only
SKILL_NAME_PATTERN = re.compile(r'^[a-z0-9-]+$')
FORBIDDEN_WORDS = ['anthropic', 'claude']


class SkillCreate(BaseModel):
    """Schema for creating a new skill (used with multipart form upload)."""

    # Note: Actual skill creation happens via file upload
    # Name and description are extracted from SKILL.md frontmatter
    pass


class SkillMetadata(BaseModel):
    """Schema for skill metadata extracted from SKILL.md frontmatter."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Skill name (lowercase, hyphens, numbers only)"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Human-readable description of what the skill does"
    )
    pip_requirements: Optional[List[str]] = Field(
        default=None,
        description="Optional list of pip packages required by this skill"
    )

    @field_validator('name')
    @classmethod
    def validate_skill_name(cls, v: str) -> str:
        if not SKILL_NAME_PATTERN.match(v):
            raise ValueError('Skill name must contain only lowercase letters, numbers, and hyphens')

        for word in FORBIDDEN_WORDS:
            if word in v.lower():
                raise ValueError(f'Skill name cannot contain reserved word: {word}')

        return v


class SkillResponse(BaseModel):
    """Schema for representing a skill from the database."""

    id: str = Field(..., description="Unique identifier of the skill")
    name: str = Field(..., description="Skill name (lowercase, hyphens, numbers only)")
    description: str = Field(..., description="Human-readable description of the skill")
    storage_path: str = Field(..., description="Path to skill zip in storage bucket")
    pip_requirements: Optional[List[str]] = Field(
        default=None,
        description="Optional list of pip packages required by this skill"
    )
    created_by: str = Field(..., description="User ID of the skill creator")
    created_at: datetime.datetime = Field(..., description="When the skill was created")
    updated_at: datetime.datetime = Field(..., description="When the skill was last updated")
    permission_level: Optional[SkillPermissionLevel] = Field(
        default=None,
        description="User's permission level for this skill"
    )
    is_public: bool = Field(
        default=False,
        description="Whether this skill has active public permissions"
    )

    class Config:
        from_attributes = True


class SkillListResponse(BaseModel):
    """Schema for list of skills response."""

    skills: List[SkillResponse] = Field(
        default_factory=list,
        description="List of skills"
    )
    total: int = Field(..., description="Total number of accessible skills")


# =====================
# Permission Schemas
# =====================


class SkillPermissionCreate(BaseModel):
    """Schema for creating a new skill permission."""

    user_id: str = Field(..., description="ID of the user to grant permission to")
    permission_level: SkillPermissionLevel = Field(
        ...,
        description="Permission level to grant"
    )


class SkillPermissionUpdate(BaseModel):
    """Schema for updating an existing skill permission."""

    permission_level: SkillPermissionLevel = Field(
        ...,
        description="New permission level"
    )


class SkillPermissionResponse(BaseModel):
    """Schema for representing a skill permission."""

    id: str = Field(..., description="Unique identifier of the permission record")
    skill_id: str = Field(..., description="ID of the skill")
    user_id: str = Field(..., description="ID of the user with permission")
    permission_level: SkillPermissionLevel = Field(..., description="Permission level")
    granted_by: str = Field(..., description="ID of the user who granted this permission")
    created_at: datetime.datetime = Field(..., description="When the permission was created")
    updated_at: datetime.datetime = Field(..., description="When the permission was last updated")
    # User info for display
    user_email: Optional[str] = Field(default=None, description="User's email address")
    user_display_name: Optional[str] = Field(default=None, description="User's display name")

    class Config:
        from_attributes = True


class SkillShareRequest(BaseModel):
    """Schema for sharing a skill with multiple users."""

    users: List[SkillPermissionCreate] = Field(
        ...,
        description="List of users and their permission levels to grant access to"
    )


class SkillShareResponse(BaseModel):
    """Schema for skill sharing response."""

    success: bool = Field(..., description="Whether the sharing operation was successful")
    shared_with: List[SkillPermissionResponse] = Field(
        default_factory=list,
        description="List of permissions that were granted"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="List of any errors that occurred"
    )


# =====================
# Skill Reference (for agent config)
# =====================


class SkillReference(BaseModel):
    """
    Reference to a skill allocated to an agent.

    This is a lightweight reference used in agent configuration,
    containing only the essential metadata needed for the system prompt.
    """

    skill_id: str = Field(..., description="UUID of the skill")
    name: str = Field(..., description="Skill name for the skills table")
    description: str = Field(..., description="Skill description for the skills table")


class SkillsConfig(BaseModel):
    """Skills configuration for an agent."""

    skills: List[SkillReference] = Field(
        default_factory=list,
        description="Skills allocated to this agent"
    )


# =====================
# Validation Response
# =====================


class SkillValidationResult(BaseModel):
    """Result of validating a skill zip file."""

    valid: bool = Field(..., description="Whether the skill zip is valid")
    name: Optional[str] = Field(default=None, description="Extracted skill name")
    description: Optional[str] = Field(default=None, description="Extracted description")
    pip_requirements: Optional[List[str]] = Field(
        default=None,
        description="Extracted pip requirements"
    )
    files: List[str] = Field(
        default_factory=list,
        description="List of files in the skill zip"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="List of validation errors"
    )
