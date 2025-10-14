"""
Permission Service - Centralized permission logic for Agent OS.

This module provides a single source of truth for permission rules and allowed actions.
All permission checks should eventually flow through this service to ensure consistency
between frontend and backend.

**Phase 3 Implementation:** This service centralizes permission logic that was previously
scattered across multiple files. It provides a standardized way to determine what actions
a user can perform on resources.

See docs/permission-rules.md for comprehensive permission system documentation.
"""

import json
import logging
from typing import List, Optional, Dict, Any

from langconnect.database.permissions import (
    GraphPermissionsManager,
    AssistantPermissionsManager,
)

log = logging.getLogger(__name__)


class PermissionService:
    """
    Centralized permission service that determines allowed actions for users on resources.

    This service is the single source of truth for permission rules. Frontend and backend
    should both rely on the allowed_actions returned by this service rather than implementing
    their own permission logic.

    **Usage:**
    ```python
    # Get allowed actions for an assistant
    actions = await PermissionService.get_allowed_actions(
        user_id="user-123",
        resource_type="assistant",
        resource_id="assistant-456"
    )
    # Returns: ["view", "chat", "edit", "delete", "share"]
    ```
    """

    @staticmethod
    async def get_allowed_actions(
        user_id: str,
        resource_type: str,  # "assistant" | "graph"
        resource_id: str,
        resource_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Get list of actions user can perform on a resource.

        This is the core method that determines what operations are permitted.
        It handles all special cases including:
        - Dev admin privileges
        - Default assistant protection
        - Permission level hierarchies
        - Service account access

        Args:
            user_id: User ID to check permissions for
            resource_type: Type of resource ("assistant" or "graph")
            resource_id: ID of the specific resource
            resource_metadata: Optional metadata for the resource (to avoid extra DB queries)

        Returns:
            List of action strings the user can perform

        **Assistant Actions:**
        - "view": Can view assistant details
        - "chat": Can interact with assistant
        - "edit": Can modify assistant configuration
        - "delete": Can delete the assistant
        - "share": Can share assistant with other users
        - "manage_access": Can grant/revoke permissions (alias for share)

        **Graph Actions:**
        - "view": Can view graph template
        - "create_assistant": Can create assistants from this graph
        - "manage_access": Can grant/revoke graph permissions to other users
        - "revoke_own": Can revoke own access (not available to dev_admins)
        """
        if resource_type == "assistant":
            return await PermissionService._get_assistant_allowed_actions(
                user_id, resource_id, resource_metadata
            )
        elif resource_type == "graph":
            return await PermissionService._get_graph_allowed_actions(
                user_id, resource_id
            )
        else:
            log.warning(f"Unknown resource_type: {resource_type}")
            return []

    @staticmethod
    async def _get_assistant_allowed_actions(
        user_id: str,
        assistant_id: str,
        resource_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Determine allowed actions for an assistant.

        **Permission Level Mapping:**
        - viewer: ["view", "chat"]
        - editor: ["view", "chat", "edit"]
        - owner: ["view", "chat", "edit", "delete", "share", "manage_access"]
        - admin (service): ["view", "chat", "edit", "delete", "share", "manage_access"]

        **Special Rules:**
        - Default assistants (metadata._x_oap_is_default === true) cannot be edited or deleted
        - Dev admins need explicit permissions (no implicit access like graphs)
        """
        # Get user's permission level for this assistant
        permission_level = await AssistantPermissionsManager.get_user_permission_for_assistant(
            user_id, assistant_id
        )

        if not permission_level:
            return []  # No access

        # Check if this is a default assistant (cannot be edited/deleted)
        is_default = False
        if resource_metadata:
            # Use provided metadata if available
            metadata_obj = resource_metadata.get("metadata", {})
            if isinstance(metadata_obj, str):
                try:
                    metadata_obj = json.loads(metadata_obj)
                except:
                    metadata_obj = {}
            is_default = metadata_obj.get("_x_oap_is_default", False)
            is_default = is_default is True or is_default == "true" or is_default == 1
        else:
            # Fetch metadata if not provided
            try:
                metadata = await AssistantPermissionsManager.get_assistant_metadata(assistant_id)
                if metadata:
                    # Note: metadata from get_assistant_metadata doesn't include LangGraph metadata
                    # We need to check if there's a metadata field that contains the _x_oap_is_default flag
                    # This might require fetching from LangGraph or checking the mirror table
                    # For now, we'll assume it's not a default unless explicitly provided
                    pass
            except Exception as e:
                log.warning(f"Could not fetch metadata for assistant {assistant_id}: {e}")

        # Base actions for all permission levels
        actions = []

        if permission_level in ["viewer", "editor", "owner", "admin"]:
            actions.extend(["view", "chat"])

        if permission_level in ["editor", "owner", "admin"]:
            # Editors can edit unless it's a default assistant
            if not is_default:
                actions.append("edit")

        if permission_level in ["owner", "admin"]:
            # Owners can delete and share unless it's a default assistant
            if not is_default:
                actions.append("delete")

            # Owners can always share (even default assistants)
            actions.extend(["share", "manage_access"])

        return actions

    @staticmethod
    async def _get_graph_allowed_actions(
        user_id: str,
        graph_id: str,
    ) -> List[str]:
        """
        Determine allowed actions for a graph.

        **Permission Level Mapping:**
        - access: ["view", "create_assistant"]
        - admin: ["view", "create_assistant", "manage_access"]

        **Special Rules:**
        - Dev admins have implicit admin access to all graphs
        - Dev admins cannot revoke their own access (system protection)
        - Users with 'access' or 'admin' can revoke their own access (except dev_admins)
        """
        # Check if user is dev_admin (implicit admin access)
        user_role = await GraphPermissionsManager.get_user_role(user_id)
        is_dev_admin = user_role == "dev_admin"

        if is_dev_admin:
            # Dev admins have full access but cannot revoke their own access
            return ["view", "create_assistant", "manage_access"]

        # Check user's explicit graph permission
        has_access = await GraphPermissionsManager.has_graph_permission(
            user_id, graph_id, "access"
        )
        has_admin = await GraphPermissionsManager.has_graph_permission(
            user_id, graph_id, "admin"
        )

        actions = []

        if has_access or has_admin:
            actions.extend(["view", "create_assistant"])

        if has_admin:
            actions.append("manage_access")

        # Users can revoke their own access (but not dev_admins)
        if (has_access or has_admin) and not is_dev_admin:
            actions.append("revoke_own")

        return actions

    @staticmethod
    async def can_user_perform_action(
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        resource_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Check if user can perform a specific action on a resource.

        This is a convenience method that wraps get_allowed_actions for
        simple yes/no checks.

        Args:
            user_id: User ID to check
            resource_type: "assistant" or "graph"
            resource_id: ID of the resource
            action: Action to check (e.g., "delete", "edit", "share")
            resource_metadata: Optional metadata to avoid extra queries

        Returns:
            True if user can perform the action, False otherwise

        Example:
        ```python
        can_delete = await PermissionService.can_user_perform_action(
            user_id="user-123",
            resource_type="assistant",
            resource_id="assistant-456",
            action="delete"
        )
        ```
        """
        allowed_actions = await PermissionService.get_allowed_actions(
            user_id, resource_type, resource_id, resource_metadata
        )
        return action in allowed_actions

    @staticmethod
    async def get_permission_summary(
        user_id: str,
        resource_type: str,
        resource_id: str,
        resource_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive permission summary for a resource.

        Returns detailed information about user's access including:
        - Permission level
        - Allowed actions
        - Special flags (is_default, is_dev_admin, etc.)

        This is useful for debugging and admin interfaces.

        Returns:
            Dictionary with permission details:
            {
                "user_id": "user-123",
                "resource_type": "assistant",
                "resource_id": "assistant-456",
                "permission_level": "owner",
                "allowed_actions": ["view", "chat", "edit", "delete", "share"],
                "is_dev_admin": False,
                "is_default": False
            }
        """
        allowed_actions = await PermissionService.get_allowed_actions(
            user_id, resource_type, resource_id, resource_metadata
        )

        summary = {
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "allowed_actions": allowed_actions,
        }

        if resource_type == "assistant":
            permission_level = await AssistantPermissionsManager.get_user_permission_for_assistant(
                user_id, resource_id
            )
            summary["permission_level"] = permission_level

            # Check if default assistant
            is_default = False
            if resource_metadata:
                metadata_obj = resource_metadata.get("metadata", {})
                if isinstance(metadata_obj, str):
                    try:
                        metadata_obj = json.loads(metadata_obj)
                    except:
                        metadata_obj = {}
                is_default = metadata_obj.get("_x_oap_is_default", False)
                is_default = is_default is True or is_default == "true" or is_default == 1
            summary["is_default"] = is_default

        elif resource_type == "graph":
            user_role = await GraphPermissionsManager.get_user_role(user_id)
            summary["is_dev_admin"] = user_role == "dev_admin"

            has_admin = await GraphPermissionsManager.has_graph_permission(
                user_id, resource_id, "admin"
            )
            has_access = await GraphPermissionsManager.has_graph_permission(
                user_id, resource_id, "access"
            )

            if has_admin:
                summary["permission_level"] = "admin"
            elif has_access:
                summary["permission_level"] = "access"
            else:
                summary["permission_level"] = None

        return summary
