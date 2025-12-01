"""
Skill permissions database manager.

This module provides the core permission management system for Skills.
All methods enforce SECURITY-CRITICAL access control.

Permission Levels:
- viewer: Can view skill details and use in agents
- editor: Can update skill content
- owner: Full control including delete and share
"""

import logging
from typing import Dict, List, Optional, Any

from langconnect.database.connection import get_db_connection

log = logging.getLogger(__name__)


PERMISSION_HIERARCHY = {
    "viewer": 0,
    "editor": 1,
    "owner": 2
}


class SkillPermissionsManager:
    """
    Manager for skill permission operations.

    **SECURITY ENFORCEMENT:** All methods in this class enforce authorization.
    """

    def __init__(self, user_id: str):
        """Initialize with the current user's ID."""
        self.user_id = user_id

    # =========================================================================
    # Permission Checks
    # =========================================================================

    async def has_permission(
        self,
        skill_id: str,
        required_level: str = "viewer"
    ) -> bool:
        """
        Check if the current user has the required permission level for a skill.

        Args:
            skill_id: UUID of the skill
            required_level: Minimum required permission (viewer, editor, owner)

        Returns:
            True if user has required permission or higher
        """
        required_rank = PERMISSION_HIERARCHY.get(required_level, 2)

        async with get_db_connection() as conn:
            # First check if skill has active public permission
            public_perm = await conn.fetchrow(
                """
                SELECT permission_level FROM langconnect.public_skill_permissions
                WHERE skill_id = $1 AND revoked_at IS NULL
                """,
                skill_id
            )

            if public_perm:
                public_rank = PERMISSION_HIERARCHY.get(public_perm["permission_level"], 0)
                if public_rank >= required_rank:
                    return True

            # Check user's direct permission
            row = await conn.fetchrow(
                """
                SELECT permission_level FROM langconnect.skill_permissions
                WHERE skill_id = $1 AND user_id = $2
                """,
                skill_id,
                self.user_id
            )

            if not row:
                return False

            user_rank = PERMISSION_HIERARCHY.get(row["permission_level"], 0)
            return user_rank >= required_rank

    async def get_permission_level(self, skill_id: str) -> Optional[str]:
        """
        Get the current user's permission level for a skill.

        Args:
            skill_id: UUID of the skill

        Returns:
            Permission level string or None if no access
        """
        async with get_db_connection() as conn:
            # Check public permission first
            public_perm = await conn.fetchrow(
                """
                SELECT permission_level FROM langconnect.public_skill_permissions
                WHERE skill_id = $1 AND revoked_at IS NULL
                """,
                skill_id
            )

            # Get user's direct permission
            user_perm = await conn.fetchrow(
                """
                SELECT permission_level FROM langconnect.skill_permissions
                WHERE skill_id = $1 AND user_id = $2
                """,
                skill_id,
                self.user_id
            )

            # Return the higher of the two permissions
            if not public_perm and not user_perm:
                return None

            public_rank = PERMISSION_HIERARCHY.get(
                public_perm["permission_level"] if public_perm else "", -1
            )
            user_rank = PERMISSION_HIERARCHY.get(
                user_perm["permission_level"] if user_perm else "", -1
            )

            if user_rank >= public_rank and user_perm:
                return user_perm["permission_level"]
            elif public_perm:
                return public_perm["permission_level"]

            return None

    # =========================================================================
    # Permission Management
    # =========================================================================

    async def grant_permission(
        self,
        skill_id: str,
        target_user_id: str,
        permission_level: str
    ) -> bool:
        """
        Grant permission to a user for a skill.

        Args:
            skill_id: UUID of the skill
            target_user_id: User ID to grant permission to
            permission_level: Permission level to grant

        Returns:
            True if permission was granted successfully
        """
        async with get_db_connection() as conn:
            await conn.execute(
                """
                INSERT INTO langconnect.skill_permissions
                    (skill_id, user_id, permission_level, granted_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (skill_id, user_id) DO UPDATE SET
                    permission_level = EXCLUDED.permission_level,
                    granted_by = EXCLUDED.granted_by,
                    updated_at = NOW()
                """,
                skill_id,
                target_user_id,
                permission_level,
                self.user_id
            )

            # Increment cache version
            await conn.execute(
                "SELECT langconnect.increment_cache_version('skills')"
            )

            return True

    async def revoke_permission(
        self,
        skill_id: str,
        target_user_id: str
    ) -> bool:
        """
        Revoke a user's permission for a skill.

        Args:
            skill_id: UUID of the skill
            target_user_id: User ID to revoke permission from

        Returns:
            True if permission was revoked
        """
        async with get_db_connection() as conn:
            result = await conn.execute(
                """
                DELETE FROM langconnect.skill_permissions
                WHERE skill_id = $1 AND user_id = $2
                """,
                skill_id,
                target_user_id
            )

            # Increment cache version
            await conn.execute(
                "SELECT langconnect.increment_cache_version('skills')"
            )

            return "DELETE 1" in result

    async def get_skill_permissions(
        self,
        skill_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all permissions for a skill.

        Args:
            skill_id: UUID of the skill

        Returns:
            List of permission records with user details
        """
        async with get_db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    sp.id,
                    sp.skill_id,
                    sp.user_id,
                    sp.permission_level,
                    sp.granted_by,
                    sp.created_at,
                    sp.updated_at,
                    ur.email as user_email,
                    ur.display_name as user_display_name
                FROM langconnect.skill_permissions sp
                LEFT JOIN langconnect.user_roles ur ON sp.user_id = ur.user_id
                WHERE sp.skill_id = $1
                ORDER BY sp.created_at ASC
                """,
                skill_id
            )
            return [dict(row) for row in rows]

    # =========================================================================
    # List Accessible Skills
    # =========================================================================

    async def get_accessible_skills(
        self,
        min_permission: str = "viewer"
    ) -> Dict[str, str]:
        """
        Get all skills the current user can access.

        Args:
            min_permission: Minimum permission level required

        Returns:
            Dictionary mapping skill_id to permission_level
        """
        min_rank = PERMISSION_HIERARCHY.get(min_permission, 0)

        async with get_db_connection() as conn:
            # Get user's direct permissions
            direct_perms = await conn.fetch(
                """
                SELECT skill_id::text, permission_level
                FROM langconnect.skill_permissions
                WHERE user_id = $1
                """,
                self.user_id
            )

            # Get public permissions
            public_perms = await conn.fetch(
                """
                SELECT skill_id::text, permission_level
                FROM langconnect.public_skill_permissions
                WHERE revoked_at IS NULL
                """
            )

            # Merge permissions, taking the higher level for each skill
            result = {}

            for row in public_perms:
                skill_id = str(row["skill_id"])
                level = row["permission_level"]
                rank = PERMISSION_HIERARCHY.get(level, 0)
                if rank >= min_rank:
                    result[skill_id] = level

            for row in direct_perms:
                skill_id = str(row["skill_id"])
                level = row["permission_level"]
                rank = PERMISSION_HIERARCHY.get(level, 0)
                if rank >= min_rank:
                    # Take higher permission if already exists from public
                    existing_rank = PERMISSION_HIERARCHY.get(result.get(skill_id, ""), -1)
                    if rank > existing_rank:
                        result[skill_id] = level

            return result


# =========================================================================
# Static Methods for Public Permissions
# =========================================================================


async def get_all_public_skill_permissions() -> List[Dict[str, Any]]:
    """Get all public skill permissions with user info."""
    async with get_db_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                psp.id,
                psp.skill_id,
                psp.permission_level,
                psp.created_at,
                psp.revoked_at,
                psp.revoke_mode,
                psp.notes,
                ur.display_name as created_by_display_name,
                ur.email as created_by_email
            FROM langconnect.public_skill_permissions psp
            LEFT JOIN langconnect.user_roles ur ON psp.created_by::text = ur.user_id
            ORDER BY psp.created_at DESC
            """
        )
        return [dict(row) for row in rows]


async def revoke_public_skill_permission(
    skill_id: str,
    revoke_mode: str
) -> Dict[str, Any]:
    """
    Revoke a public skill permission.

    Args:
        skill_id: UUID of the skill
        revoke_mode: Either 'revoke_all' or 'future_only'

    Returns:
        Dictionary with revocation details
    """
    async with get_db_connection() as conn:
        async with conn.transaction():
            # Mark the public permission as revoked
            await conn.execute(
                """
                UPDATE langconnect.public_skill_permissions
                SET revoked_at = NOW(), revoke_mode = $1
                WHERE skill_id = $2 AND revoked_at IS NULL
                """,
                revoke_mode,
                skill_id
            )

            revoked_count = 0
            # If revoke_all mode, remove existing user permissions from public grants
            if revoke_mode == 'revoke_all':
                result = await conn.execute(
                    """
                    DELETE FROM langconnect.skill_permissions
                    WHERE skill_id = $1 AND granted_by = 'system:public'
                    """,
                    skill_id
                )
                if hasattr(result, 'split'):
                    revoked_count = int(result.split()[-1]) if result.split()[-1].isdigit() else 0

            # Increment cache version
            await conn.execute(
                "SELECT langconnect.increment_cache_version('skills')"
            )

            return {
                "skill_id": skill_id,
                "status": "revoked",
                "mode": revoke_mode,
                "revoked_user_count": revoked_count
            }
