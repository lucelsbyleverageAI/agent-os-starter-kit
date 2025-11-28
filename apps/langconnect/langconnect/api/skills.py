"""
API endpoints for Skills management.

Skills are modular capability packages that extend agent functionality.
This module provides CRUD operations and permission management for skills.
"""

import logging
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.config import SUPABASE_URL, SUPABASE_PUBLIC_URL, SUPABASE_KEY
from langconnect.database.connection import get_db_connection
from langconnect.database.skill_permissions import SkillPermissionsManager
from langconnect.database.user_roles import UserRoleManager
from langconnect.database.notifications import NotificationManager
from langconnect.models.skill import (
    SkillResponse,
    SkillListResponse,
    SkillPermissionResponse,
    SkillShareRequest,
    SkillShareResponse,
    SkillValidationResult,
    SkillPermissionLevel,
)
from langconnect.services.skill_validation import (
    validate_skill_zip,
    extract_skill_metadata,
)

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/skills",
    tags=["Skills"],
)


# ============================================================================
# Helper Functions
# ============================================================================


async def get_supabase_client():
    """Get Supabase client for internal storage operations (uploads, deletes)."""
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def rewrite_signed_url_for_external_access(signed_url: str) -> str:
    """Rewrite a signed URL to be externally accessible.

    Inside Docker, Supabase SDK generates URLs with internal hostname (kong:8000).
    For external clients (like LangGraph running on host), we need to rewrite
    these to use the public URL (localhost:8000).

    Args:
        signed_url: The signed URL with internal hostname

    Returns:
        The signed URL with external hostname
    """
    if not signed_url:
        return signed_url

    # Replace internal Docker hostname with external hostname
    # SUPABASE_URL is internal (http://kong:8000)
    # SUPABASE_PUBLIC_URL is external (http://localhost:8000)
    if SUPABASE_URL and SUPABASE_PUBLIC_URL and SUPABASE_URL != SUPABASE_PUBLIC_URL:
        rewritten = signed_url.replace(SUPABASE_URL, SUPABASE_PUBLIC_URL)
        if rewritten != signed_url:
            log.info(f"[skills:download] Rewrote signed URL from internal to external: {SUPABASE_URL} -> {SUPABASE_PUBLIC_URL}")
        return rewritten

    return signed_url


async def get_skill_by_id(skill_id: str) -> Optional[dict]:
    """Get skill by ID from database."""
    async with get_db_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                id, name, description, storage_path, pip_requirements,
                created_by, created_at, updated_at
            FROM langconnect.skills
            WHERE id = $1
            """,
            skill_id
        )
        return dict(row) if row else None


async def is_skill_public(skill_id: str) -> bool:
    """Check if a skill has active public permissions."""
    async with get_db_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM langconnect.public_skill_permissions
            WHERE skill_id = $1 AND revoked_at IS NULL
            """,
            skill_id
        )
        return row is not None


# ============================================================================
# Validation Endpoint
# ============================================================================


@router.post("/validate", response_model=SkillValidationResult)
async def validate_skill(
    file: UploadFile = File(...),
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    Validate a skill zip file without uploading.

    This endpoint performs all validation checks on the zip file:
    - Verifies it's a valid zip
    - Checks for SKILL.md at root
    - Validates frontmatter (name, description)
    - Extracts pip requirements

    Returns validation result with extracted metadata or errors.
    """
    if not file.filename or not file.filename.endswith('.zip'):
        return SkillValidationResult(
            valid=False,
            errors=["File must be a .zip file"]
        )

    content = await file.read()
    result = await validate_skill_zip(content)
    return result


# ============================================================================
# CRUD Endpoints
# ============================================================================


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    file: UploadFile = File(...),
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    Upload a new skill.

    The skill must be a zip file containing:
    - SKILL.md at root with YAML frontmatter (name, description, optional pip_requirements)
    - Optional scripts/ directory for Python scripts
    - Optional resources/ directory for static files

    The user uploading becomes the owner of the skill.
    """
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=400,
            detail="File must be a .zip file"
        )

    # Read and validate the file
    content = await file.read()
    validation = await validate_skill_zip(content)

    if not validation.valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Invalid skill package", "errors": validation.errors}
        )

    # Extract metadata
    metadata = extract_skill_metadata(content)
    if not metadata:
        raise HTTPException(
            status_code=400,
            detail="Failed to extract skill metadata"
        )

    # Check if user already has a skill with this name
    async with get_db_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT id FROM langconnect.skills
            WHERE name = $1 AND created_by = $2
            """,
            metadata.name,
            actor.identity
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"You already have a skill named '{metadata.name}'"
            )

    # Create database record first to get the ID
    async with get_db_connection() as conn:
        async with conn.transaction():
            # Insert skill record
            row = await conn.fetchrow(
                """
                INSERT INTO langconnect.skills
                    (name, description, storage_path, pip_requirements, created_by)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, name, description, storage_path, pip_requirements,
                          created_by, created_at, updated_at
                """,
                metadata.name,
                metadata.description,
                "",  # Will update after upload
                metadata.pip_requirements,
                actor.identity
            )
            skill_id = str(row["id"])

            # Create owner permission
            await conn.execute(
                """
                INSERT INTO langconnect.skill_permissions
                    (skill_id, user_id, permission_level, granted_by)
                VALUES ($1, $2, 'owner', $3)
                """,
                skill_id,
                actor.identity,
                actor.identity
            )

            # Increment cache version
            await conn.execute(
                "SELECT langconnect.increment_cache_version('skills')"
            )

    # Upload to storage
    storage_path = f"{skill_id}/skill.zip"
    try:
        supabase = await get_supabase_client()
        supabase.storage.from_("skills").upload(
            path=storage_path,
            file=content,
            file_options={"content-type": "application/zip"}
        )
    except Exception as e:
        # Rollback: delete the skill record
        async with get_db_connection() as conn:
            await conn.execute(
                "DELETE FROM langconnect.skills WHERE id = $1",
                skill_id
            )
        log.error(f"Failed to upload skill to storage: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to upload skill to storage"
        )

    # Update storage path
    async with get_db_connection() as conn:
        await conn.execute(
            "UPDATE langconnect.skills SET storage_path = $1 WHERE id = $2",
            storage_path,
            skill_id
        )

    log.info(f"User '{actor.identity}' created skill '{metadata.name}' with ID '{skill_id}'")

    return SkillResponse(
        id=skill_id,
        name=metadata.name,
        description=metadata.description,
        storage_path=storage_path,
        pip_requirements=metadata.pip_requirements,
        created_by=actor.identity,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        permission_level=SkillPermissionLevel.OWNER,
        is_public=False
    )


@router.get("", response_model=SkillListResponse)
async def list_skills(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    List all skills accessible to the current user.

    Returns skills the user owns, has been shared access to, or are public.
    """
    permissions_manager = SkillPermissionsManager(actor.identity)
    accessible_skills = await permissions_manager.get_accessible_skills()

    if not accessible_skills:
        return SkillListResponse(skills=[], total=0)

    skill_ids = list(accessible_skills.keys())

    async with get_db_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                s.id, s.name, s.description, s.storage_path, s.pip_requirements,
                s.created_by, s.created_at, s.updated_at,
                CASE WHEN psp.id IS NOT NULL THEN true ELSE false END as is_public
            FROM langconnect.skills s
            LEFT JOIN langconnect.public_skill_permissions psp
                ON s.id = psp.skill_id AND psp.revoked_at IS NULL
            WHERE s.id = ANY($1::uuid[])
            ORDER BY s.created_at DESC
            """,
            skill_ids
        )

    skills = []
    for row in rows:
        skill_id = str(row["id"])
        skills.append(SkillResponse(
            id=skill_id,
            name=row["name"],
            description=row["description"],
            storage_path=row["storage_path"],
            pip_requirements=row["pip_requirements"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            permission_level=SkillPermissionLevel(accessible_skills[skill_id]),
            is_public=row["is_public"]
        ))

    return SkillListResponse(skills=skills, total=len(skills))


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """Get a specific skill by ID."""
    permissions_manager = SkillPermissionsManager(actor.identity)

    if not await permissions_manager.has_permission(skill_id, "viewer"):
        raise HTTPException(status_code=404, detail="Skill not found")

    skill = await get_skill_by_id(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    permission_level = await permissions_manager.get_permission_level(skill_id)
    is_public = await is_skill_public(skill_id)

    return SkillResponse(
        id=str(skill["id"]),
        name=skill["name"],
        description=skill["description"],
        storage_path=skill["storage_path"],
        pip_requirements=skill["pip_requirements"],
        created_by=skill["created_by"],
        created_at=skill["created_at"],
        updated_at=skill["updated_at"],
        permission_level=SkillPermissionLevel(permission_level) if permission_level else None,
        is_public=is_public
    )


@router.get("/{skill_id}/download")
async def download_skill(
    skill_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    Get a signed URL to download the skill zip file.

    Used by LangGraph agents to fetch skill files for sandbox mounting.
    """
    permissions_manager = SkillPermissionsManager(actor.identity)

    if not await permissions_manager.has_permission(skill_id, "viewer"):
        raise HTTPException(status_code=404, detail="Skill not found")

    skill = await get_skill_by_id(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    if not skill["storage_path"]:
        raise HTTPException(status_code=404, detail="Skill file not found")

    try:
        # Use internal client to create signed URL, then rewrite for external access
        log.info(f"[skills:download] Getting signed URL for skill {skill_id}, storage_path: {skill['storage_path']}")
        supabase = await get_supabase_client()
        signed_url = supabase.storage.from_("skills").create_signed_url(
            skill["storage_path"],
            expires_in=3600  # 1 hour
        )
        # Rewrite URL from internal (kong:8000) to external (localhost:8000)
        download_url = rewrite_signed_url_for_external_access(signed_url["signedURL"])
        log.info(f"[skills:download] Generated signed URL for skill {skill_id}: {download_url[:80]}...")
        return {"download_url": download_url}
    except Exception as e:
        log.error(f"Failed to create signed URL for skill {skill_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate download URL"
        )


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    file: UploadFile = File(...),
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    Update a skill by re-uploading a new zip file.

    Requires editor permission. The skill name cannot be changed.
    """
    permissions_manager = SkillPermissionsManager(actor.identity)

    if not await permissions_manager.has_permission(skill_id, "editor"):
        raise HTTPException(status_code=403, detail="Forbidden")

    skill = await get_skill_by_id(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=400,
            detail="File must be a .zip file"
        )

    # Read and validate
    content = await file.read()
    validation = await validate_skill_zip(content)

    if not validation.valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Invalid skill package", "errors": validation.errors}
        )

    # Verify name matches existing skill
    metadata = extract_skill_metadata(content)
    if not metadata:
        raise HTTPException(
            status_code=400,
            detail="Failed to extract skill metadata"
        )

    if metadata.name != skill["name"]:
        raise HTTPException(
            status_code=400,
            detail=f"Skill name cannot be changed. Expected '{skill['name']}', got '{metadata.name}'"
        )

    # Upload new file (overwrite)
    storage_path = skill["storage_path"] or f"{skill_id}/skill.zip"
    try:
        supabase = await get_supabase_client()
        # Remove old file first
        try:
            supabase.storage.from_("skills").remove([storage_path])
        except Exception:
            pass  # File might not exist
        # Upload new file
        supabase.storage.from_("skills").upload(
            path=storage_path,
            file=content,
            file_options={"content-type": "application/zip"}
        )
    except Exception as e:
        log.error(f"Failed to upload skill update: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to upload skill"
        )

    # Update database
    async with get_db_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE langconnect.skills
            SET description = $1, pip_requirements = $2, storage_path = $3, updated_at = NOW()
            WHERE id = $4
            RETURNING id, name, description, storage_path, pip_requirements,
                      created_by, created_at, updated_at
            """,
            metadata.description,
            metadata.pip_requirements,
            storage_path,
            skill_id
        )

        # Increment cache version
        await conn.execute(
            "SELECT langconnect.increment_cache_version('skills')"
        )

    permission_level = await permissions_manager.get_permission_level(skill_id)
    is_public = await is_skill_public(skill_id)

    log.info(f"User '{actor.identity}' updated skill '{skill_id}'")

    return SkillResponse(
        id=str(row["id"]),
        name=row["name"],
        description=row["description"],
        storage_path=row["storage_path"],
        pip_requirements=row["pip_requirements"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        permission_level=SkillPermissionLevel(permission_level) if permission_level else None,
        is_public=is_public
    )


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    Delete a skill.

    Requires owner permission.
    """
    permissions_manager = SkillPermissionsManager(actor.identity)

    if not await permissions_manager.has_permission(skill_id, "owner"):
        raise HTTPException(status_code=403, detail="Forbidden")

    skill = await get_skill_by_id(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Delete from storage
    if skill["storage_path"]:
        try:
            supabase = await get_supabase_client()
            supabase.storage.from_("skills").remove([skill["storage_path"]])
        except Exception as e:
            log.warning(f"Failed to delete skill file from storage: {e}")

    # Delete from database (cascade deletes permissions)
    async with get_db_connection() as conn:
        await conn.execute(
            "DELETE FROM langconnect.skills WHERE id = $1",
            skill_id
        )

        # Increment cache version
        await conn.execute(
            "SELECT langconnect.increment_cache_version('skills')"
        )

    log.info(f"User '{actor.identity}' deleted skill '{skill_id}'")


# ============================================================================
# Permission Endpoints
# ============================================================================


@router.post("/{skill_id}/share", response_model=SkillShareResponse)
async def share_skill(
    skill_id: str,
    request: SkillShareRequest,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    Share a skill with users by creating notifications.

    Permissions are granted when the recipient accepts the notification.
    Requires owner permission.
    """
    permissions_manager = SkillPermissionsManager(actor.identity)

    if not await permissions_manager.has_permission(skill_id, "owner"):
        raise HTTPException(status_code=403, detail="Forbidden")

    skill = await get_skill_by_id(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Create notifications for each user (like collections)
    notification_manager = NotificationManager()
    errors = []

    for user_perm in request.users:
        try:
            # Verify user exists
            async with get_db_connection() as conn:
                user = await conn.fetchrow(
                    "SELECT user_id FROM langconnect.user_roles WHERE user_id = $1",
                    user_perm.user_id
                )
                if not user:
                    errors.append(f"User not found: {user_perm.user_id}")
                    continue

            # Create notification with skill metadata
            await notification_manager.create_notification(
                recipient_user_id=user_perm.user_id,
                notification_type="skill_share",
                resource_id=str(skill_id),
                resource_type="skill",
                permission_level=user_perm.permission_level.value,
                sender_user_id=actor.identity,
                sender_display_name=actor.identity,  # TODO: Get actual display name
                resource_name=skill["name"],
                resource_description=skill.get("description")
            )

            log.info(
                f"User '{actor.identity}' created skill share notification "
                f"for user '{user_perm.user_id}' on skill '{skill_id}'"
            )

        except Exception as e:
            errors.append(f"Failed to share with {user_perm.user_id}: {str(e)}")

    # Return successful response - permissions will be created when notifications are accepted
    return SkillShareResponse(
        success=len(errors) == 0,
        shared_with=[],  # No immediate permissions - created when notifications are accepted
        errors=errors
    )


@router.get("/{skill_id}/permissions", response_model=List[SkillPermissionResponse])
async def get_skill_permissions(
    skill_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    Get all permissions for a skill.

    Requires viewer permission.
    """
    permissions_manager = SkillPermissionsManager(actor.identity)

    if not await permissions_manager.has_permission(skill_id, "viewer"):
        raise HTTPException(status_code=404, detail="Skill not found")

    perms = await permissions_manager.get_skill_permissions(skill_id)

    return [
        SkillPermissionResponse(
            id=str(perm["id"]),
            skill_id=str(perm["skill_id"]),
            user_id=perm["user_id"],
            permission_level=SkillPermissionLevel(perm["permission_level"]),
            granted_by=perm["granted_by"],
            created_at=perm["created_at"],
            updated_at=perm["updated_at"],
            user_email=perm.get("user_email"),
            user_display_name=perm.get("user_display_name")
        )
        for perm in perms
    ]


@router.delete("/{skill_id}/permissions/{user_id}", status_code=204)
async def revoke_skill_permission(
    skill_id: str,
    user_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    Revoke a user's permission for a skill.

    Requires owner permission.
    """
    permissions_manager = SkillPermissionsManager(actor.identity)

    if not await permissions_manager.has_permission(skill_id, "owner"):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Cannot revoke own owner permission
    if user_id == actor.identity:
        raise HTTPException(
            status_code=400,
            detail="Cannot revoke your own owner permission"
        )

    success = await permissions_manager.revoke_permission(skill_id, user_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Permission not found"
        )

    log.info(f"User '{actor.identity}' revoked permission for user '{user_id}' on skill '{skill_id}'")


# ============================================================================
# Admin Endpoints
# ============================================================================


@router.get("/admin/all", response_model=SkillListResponse)
async def list_all_skills(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)] = None,
):
    """
    List all skills (admin only).
    """
    user_role_manager = UserRoleManager(actor.identity)
    if not await user_role_manager.is_dev_admin():
        raise HTTPException(status_code=403, detail="Forbidden: Requires dev_admin role")

    async with get_db_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                s.id, s.name, s.description, s.storage_path, s.pip_requirements,
                s.created_by, s.created_at, s.updated_at,
                CASE WHEN psp.id IS NOT NULL THEN true ELSE false END as is_public
            FROM langconnect.skills s
            LEFT JOIN langconnect.public_skill_permissions psp
                ON s.id = psp.skill_id AND psp.revoked_at IS NULL
            ORDER BY s.created_at DESC
            """
        )

    skills = []
    for row in rows:
        skills.append(SkillResponse(
            id=str(row["id"]),
            name=row["name"],
            description=row["description"],
            storage_path=row["storage_path"],
            pip_requirements=row["pip_requirements"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            permission_level=SkillPermissionLevel.OWNER,  # Admin has full access
            is_public=row["is_public"]
        ))

    return SkillListResponse(skills=skills, total=len(skills))
