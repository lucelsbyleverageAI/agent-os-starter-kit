"""
User ID mapper for translating user IDs between environments.

Handles email-based matching and explicit UUID mappings.
"""

import logging
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import TransferConfig

logger = logging.getLogger(__name__)


class UserMappingError(Exception):
    """User mapping-related errors."""
    pass


class UserMapper:
    """Maps user IDs between source and target environments."""

    def __init__(
        self,
        config: TransferConfig,
        source_env: str,
        target_env: str,
        target_conn_params: Dict[str, Any]
    ):
        """
        Initialize user mapper.

        Args:
            config: Transfer configuration
            source_env: Source environment name
            target_env: Target environment name
            target_conn_params: Database connection params for target environment
        """
        self.config = config
        self.source_env = source_env
        self.target_env = target_env
        self.target_conn_params = target_conn_params

        # Get configuration
        self.explicit_mappings = config.get_explicit_mappings(source_env, target_env)
        self.default_owner_email = config.get_default_owner(target_env)
        self.strategy = config.get_permission_strategy()

        # Cache for target environment users (email -> user data)
        self._target_users_cache: Optional[Dict[str, Dict]] = None

    def _get_target_connection(self):
        """Create connection to target database."""
        return psycopg2.connect(**self.target_conn_params)

    def _load_target_users(self):
        """Load all users from target environment and cache by email."""
        if self._target_users_cache is not None:
            return self._target_users_cache

        logger.debug(f"Loading users from target environment: {self.target_env}")

        with self._get_target_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        user_id,
                        email,
                        display_name,
                        role
                    FROM langconnect.user_roles
                """)
                users = [dict(row) for row in cur.fetchall()]

        # Cache by email (lowercase for case-insensitive matching)
        self._target_users_cache = {}
        for user in users:
            if user["email"]:
                email_key = user["email"].lower()
                self._target_users_cache[email_key] = user

        logger.debug(f"Loaded {len(self._target_users_cache)} users from target")
        return self._target_users_cache

    def _find_user_by_email(self, email: str) -> Optional[Dict]:
        """
        Find user in target environment by email.

        Args:
            email: Email address to search for

        Returns:
            User dict if found, None otherwise
        """
        if not email:
            return None

        users_cache = self._load_target_users()
        return users_cache.get(email.lower())

    def _get_default_owner(self) -> Optional[Dict]:
        """Get default owner user from target environment."""
        if not self.default_owner_email:
            return None

        default_owner = self._find_user_by_email(self.default_owner_email)
        if not default_owner:
            logger.warning(
                f"Default owner email '{self.default_owner_email}' not found in target environment"
            )
        return default_owner

    def map_permission(
        self,
        source_permission: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Map a single permission from source to target environment.

        Args:
            source_permission: Permission dict with keys:
                - user_id: Source user UUID
                - email: Source user email (optional)
                - permission_level: owner/editor/viewer
                - granted_by: Who granted the permission

        Returns:
            Mapped permission dict with target user_id, or None if should skip

        Resolution order:
        1. Skip if system-granted and strategy says to skip
        2. Check explicit UUID mapping
        3. Try email-based matching
        4. Fallback to default owner
        5. Apply strategy (skip/fail/assign)
        """
        source_user_id = source_permission["user_id"]
        source_email = source_permission.get("email")
        permission_level = source_permission["permission_level"]
        granted_by = source_permission.get("granted_by", "")

        # Skip system permissions if configured
        if self.strategy.get("skip_system_permissions") and granted_by.startswith("system:"):
            logger.debug(f"Skipping system permission for {source_user_id} (granted by {granted_by})")
            return None

        # 1. Try explicit UUID mapping
        if source_user_id in self.explicit_mappings:
            target_user_id = self.explicit_mappings[source_user_id]
            logger.debug(f"Explicit mapping: {source_user_id} -> {target_user_id}")

            return {
                "user_id": target_user_id,
                "permission_level": permission_level,
                "granted_by": granted_by,
                "mapping_method": "explicit_uuid"
            }

        # 2. Try email-based matching
        if source_email:
            target_user = self._find_user_by_email(source_email)
            if target_user:
                logger.debug(f"Email match: {source_email} -> {target_user['user_id']}")

                return {
                    "user_id": target_user["user_id"],
                    "permission_level": permission_level,
                    "granted_by": granted_by,
                    "mapping_method": "email_match",
                    "matched_email": source_email
                }

        # 3. User not found - apply strategy
        missing_action = self.strategy.get("missing_user_action", "assign_to_default_owner")

        if missing_action == "fail":
            raise UserMappingError(
                f"User {source_user_id} (email: {source_email}) not found in target environment. "
                f"Strategy is 'fail' - aborting."
            )

        elif missing_action == "skip":
            logger.warning(
                f"User {source_user_id} (email: {source_email}) not found in target - skipping permission"
            )
            return None

        elif missing_action == "assign_to_default_owner":
            default_owner = self._get_default_owner()
            if not default_owner:
                raise UserMappingError(
                    f"User {source_user_id} (email: {source_email}) not found, "
                    f"and no default owner configured for {self.target_env}"
                )

            # Determine permission level for default owner
            if self.strategy.get("preserve_permission_levels"):
                final_level = permission_level
            else:
                # Promote to owner if not preserving levels
                final_level = "owner"

            logger.info(
                f"User {source_user_id} (email: {source_email}) not found - "
                f"assigning to default owner {default_owner['email']} as {final_level}"
            )

            return {
                "user_id": default_owner["user_id"],
                "permission_level": final_level,
                "granted_by": "system:import_default_owner",
                "mapping_method": "default_owner_fallback",
                "original_user": source_user_id,
                "original_email": source_email
            }

        else:
            raise UserMappingError(f"Unknown missing_user_action: {missing_action}")

    def map_permissions(
        self,
        source_permissions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Map all permissions from source to target environment.

        Args:
            source_permissions: List of permission dicts from source

        Returns:
            List of mapped permissions (may be shorter if some were skipped)

        Raises:
            UserMappingError: If strategy is 'fail' and user not found
        """
        mapped = []
        stats = {
            "total": len(source_permissions),
            "explicit_uuid": 0,
            "email_match": 0,
            "default_owner_fallback": 0,
            "skipped_system": 0,
            "skipped_missing": 0
        }

        for perm in source_permissions:
            try:
                mapped_perm = self.map_permission(perm)
                if mapped_perm:
                    mapped.append(mapped_perm)
                    method = mapped_perm.get("mapping_method", "unknown")
                    stats[method] = stats.get(method, 0) + 1
                else:
                    stats["skipped_system"] += 1

            except UserMappingError as e:
                # Re-raise if strategy is 'fail'
                if self.strategy.get("missing_user_action") == "fail":
                    raise
                # Otherwise log and continue
                logger.error(f"Failed to map permission: {e}")
                stats["skipped_missing"] += 1

        logger.info(f"Permission mapping stats: {stats}")
        return mapped

    def get_mapping_report(self) -> Dict[str, Any]:
        """Get a report of available mappings and configuration."""
        target_users = self._load_target_users()

        return {
            "source_env": self.source_env,
            "target_env": self.target_env,
            "strategy": self.strategy,
            "explicit_mappings_count": len(self.explicit_mappings),
            "target_users_count": len(target_users),
            "default_owner": self.default_owner_email,
            "target_user_emails": [user["email"] for user in target_users.values()]
        }


def create_user_mapper(
    config: TransferConfig,
    source_env: str,
    target_env: str,
    target_conn_params: Dict[str, Any]
) -> UserMapper:
    """
    Create a UserMapper instance.

    Args:
        config: Transfer configuration
        source_env: Source environment name
        target_env: Target environment name
        target_conn_params: Database connection parameters for target

    Returns:
        UserMapper instance
    """
    return UserMapper(config, source_env, target_env, target_conn_params)
