from typing import Optional
import logging
from uuid import UUID

from langconnect.database.connection import get_db_connection

# Standard Python logger for general logging
log = logging.getLogger(__name__)


class DefaultAssistantManager:
    """Manager for user default assistant operations."""

    def __init__(self, user_id: str):
        """Initialize DefaultAssistantManager.

        Args:
            user_id: The ID of the user performing the operations
        """
        self.user_id = user_id

    async def get_default_assistant(self) -> Optional[dict]:
        """Get user's default assistant.

        Returns:
            Default assistant information or None if not set
        """
        async with get_db_connection() as connection:
            query = """
                SELECT uda.user_id, uda.assistant_id, uda.created_at, uda.updated_at,
                       am.name as assistant_name, am.graph_id
                FROM langconnect.user_default_assistants uda
                LEFT JOIN langconnect.assistants_mirror am ON uda.assistant_id = am.assistant_id
                WHERE uda.user_id = $1
            """
            result = await connection.fetchrow(query, self.user_id)

            if result:
                return dict(result)
            return None

    async def set_default_assistant(self, assistant_id: UUID) -> dict:
        """Set or update user's default assistant.

        Args:
            assistant_id: Assistant ID to set as default

        Returns:
            Default assistant information after update

        Raises:
            PermissionError: If user doesn't have permission to the assistant
            ValueError: If assistant doesn't exist
        """
        async with get_db_connection() as connection:
            # First verify user has permission to this assistant
            permission_check = """
                SELECT 1 FROM langconnect.assistant_permissions
                WHERE assistant_id = $1 AND user_id = $2
            """
            has_permission = await connection.fetchval(permission_check, assistant_id, self.user_id)

            if not has_permission:
                raise PermissionError(
                    f"User {self.user_id} does not have permission to assistant {assistant_id}"
                )

            # Verify assistant exists
            assistant_check = """
                SELECT 1 FROM langconnect.assistants_mirror
                WHERE assistant_id = $1
            """
            assistant_exists = await connection.fetchval(assistant_check, assistant_id)

            if not assistant_exists:
                raise ValueError(f"Assistant {assistant_id} does not exist")

            # Set as default (upsert)
            query = """
                INSERT INTO langconnect.user_default_assistants (user_id, assistant_id)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET
                    assistant_id = EXCLUDED.assistant_id,
                    updated_at = NOW()
                RETURNING user_id, assistant_id, created_at, updated_at
            """
            result = await connection.fetchrow(query, self.user_id, assistant_id)

            if result:
                log.info(f"Set default assistant for user {self.user_id} to {assistant_id}")
                return dict(result)

            raise RuntimeError("Failed to set default assistant")

    async def clear_default_assistant(self) -> bool:
        """Clear user's default assistant.

        Returns:
            True if default was cleared, False if no default was set
        """
        async with get_db_connection() as connection:
            query = """
                DELETE FROM langconnect.user_default_assistants
                WHERE user_id = $1
            """
            result = await connection.execute(query, self.user_id)

            # Check if any row was deleted
            deleted = result == "DELETE 1"

            if deleted:
                log.info(f"Cleared default assistant for user {self.user_id}")

            return deleted
