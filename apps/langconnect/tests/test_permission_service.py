"""
Integration tests for PermissionService.

These tests verify that the centralized permission logic works correctly
for all permission levels and special cases.
"""

import pytest
from unittest.mock import AsyncMock, patch
from langconnect.services.permission_service import PermissionService


# ============================================================================
# Assistant Permission Tests
# ============================================================================


@pytest.mark.asyncio
async def test_owner_can_delete_non_default_assistant():
    """Owner can delete custom assistant (not marked as default)."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="owner",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="owner-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {}},  # Not a default assistant
        )

        assert "delete" in actions
        assert "edit" in actions
        assert "share" in actions
        assert "manage_access" in actions
        assert "view" in actions
        assert "chat" in actions


@pytest.mark.asyncio
async def test_owner_cannot_delete_default_assistant():
    """Owner cannot delete default assistant (system-managed)."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="owner",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="owner-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {"_x_oap_is_default": True}},
        )

        # Cannot delete or edit, but can still share
        assert "delete" not in actions
        assert "edit" not in actions
        assert "share" in actions
        assert "manage_access" in actions
        assert "view" in actions
        assert "chat" in actions


@pytest.mark.asyncio
async def test_owner_cannot_edit_default_assistant():
    """Owner cannot edit default assistant."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="owner",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="owner-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {"_x_oap_is_default": "true"}},  # String variant
        )

        assert "edit" not in actions
        assert "delete" not in actions


@pytest.mark.asyncio
async def test_editor_can_edit_custom_assistant():
    """Editor can edit custom assistant."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="editor",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="editor-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {}},
        )

        assert "edit" in actions
        assert "view" in actions
        assert "chat" in actions
        # But cannot delete or share
        assert "delete" not in actions
        assert "share" not in actions
        assert "manage_access" not in actions


@pytest.mark.asyncio
async def test_editor_cannot_edit_default_assistant():
    """Editor cannot edit default assistant."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="editor",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="editor-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {"_x_oap_is_default": True}},
        )

        assert "edit" not in actions
        # But can still view and chat
        assert "view" in actions
        assert "chat" in actions


@pytest.mark.asyncio
async def test_viewer_has_read_only_access():
    """Viewer can only view and chat with assistant."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="viewer",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="viewer-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {}},
        )

        assert "view" in actions
        assert "chat" in actions
        # Cannot edit, delete, or share
        assert "edit" not in actions
        assert "delete" not in actions
        assert "share" not in actions
        assert "manage_access" not in actions


@pytest.mark.asyncio
async def test_no_permission_returns_empty_actions():
    """User with no permission gets empty actions list."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value=None,
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="no-access-user",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {}},
        )

        assert actions == []


@pytest.mark.asyncio
async def test_default_assistant_with_numeric_flag():
    """Default assistant detection works with numeric 1."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="owner",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="owner-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {"_x_oap_is_default": 1}},  # Numeric variant
        )

        assert "edit" not in actions
        assert "delete" not in actions


# ============================================================================
# Graph Permission Tests
# ============================================================================


@pytest.mark.asyncio
async def test_dev_admin_implicit_graph_access():
    """Dev admin has implicit admin access to all graphs."""
    with patch(
        "langconnect.database.permissions.GraphPermissionsManager.get_user_role",
        return_value="dev_admin",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="dev-admin-user",
            resource_type="graph",
            resource_id="deepagent",
        )

        assert "view" in actions
        assert "create_assistant" in actions
        assert "manage_access" in actions
        # But cannot revoke own access (system protection)
        assert "revoke_own" not in actions


@pytest.mark.asyncio
async def test_graph_admin_can_manage_access():
    """Graph admin can manage access permissions."""
    with patch(
        "langconnect.database.permissions.GraphPermissionsManager.get_user_role",
        return_value="user",
    ), patch(
        "langconnect.database.permissions.GraphPermissionsManager.has_graph_permission",
        side_effect=lambda user_id, graph_id, level: level == "admin",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="user-123",
            resource_type="graph",
            resource_id="deepagent",
        )

        assert "view" in actions
        assert "create_assistant" in actions
        assert "manage_access" in actions
        # Regular admin can revoke own access
        assert "revoke_own" in actions


@pytest.mark.asyncio
async def test_graph_access_can_create_assistants():
    """User with 'access' permission can create assistants."""
    with patch(
        "langconnect.database.permissions.GraphPermissionsManager.get_user_role",
        return_value="user",
    ), patch(
        "langconnect.database.permissions.GraphPermissionsManager.has_graph_permission",
        side_effect=lambda user_id, graph_id, level: level == "access",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="user-123",
            resource_type="graph",
            resource_id="deepagent",
        )

        assert "view" in actions
        assert "create_assistant" in actions
        assert "revoke_own" in actions
        # But cannot manage access
        assert "manage_access" not in actions


@pytest.mark.asyncio
async def test_graph_no_permission_returns_empty():
    """User with no graph permission gets empty actions."""
    with patch(
        "langconnect.database.permissions.GraphPermissionsManager.get_user_role",
        return_value="user",
    ), patch(
        "langconnect.database.permissions.GraphPermissionsManager.has_graph_permission",
        return_value=False,
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="user-123",
            resource_type="graph",
            resource_id="deepagent",
        )

        assert actions == []


# ============================================================================
# Convenience Method Tests
# ============================================================================


@pytest.mark.asyncio
async def test_can_user_perform_action_returns_true():
    """can_user_perform_action returns True when action is allowed."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="owner",
    ):
        can_delete = await PermissionService.can_user_perform_action(
            user_id="owner-123",
            resource_type="assistant",
            resource_id="assistant-456",
            action="delete",
            resource_metadata={"metadata": {}},
        )

        assert can_delete is True


@pytest.mark.asyncio
async def test_can_user_perform_action_returns_false():
    """can_user_perform_action returns False when action is not allowed."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="viewer",
    ):
        can_delete = await PermissionService.can_user_perform_action(
            user_id="viewer-123",
            resource_type="assistant",
            resource_id="assistant-456",
            action="delete",
            resource_metadata={"metadata": {}},
        )

        assert can_delete is False


@pytest.mark.asyncio
async def test_get_permission_summary_for_assistant():
    """get_permission_summary returns comprehensive assistant info."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="owner",
    ):
        summary = await PermissionService.get_permission_summary(
            user_id="owner-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {"_x_oap_is_default": False}},
        )

        assert summary["user_id"] == "owner-123"
        assert summary["resource_type"] == "assistant"
        assert summary["resource_id"] == "assistant-456"
        assert summary["permission_level"] == "owner"
        assert summary["is_default"] is False
        assert "delete" in summary["allowed_actions"]
        assert "edit" in summary["allowed_actions"]


@pytest.mark.asyncio
async def test_get_permission_summary_for_graph():
    """get_permission_summary returns comprehensive graph info."""
    with patch(
        "langconnect.database.permissions.GraphPermissionsManager.get_user_role",
        return_value="dev_admin",
    ):
        summary = await PermissionService.get_permission_summary(
            user_id="dev-admin-user",
            resource_type="graph",
            resource_id="deepagent",
        )

        assert summary["user_id"] == "dev-admin-user"
        assert summary["resource_type"] == "graph"
        assert summary["resource_id"] == "deepagent"
        assert summary["is_dev_admin"] is True
        assert "manage_access" in summary["allowed_actions"]
        assert "revoke_own" not in summary["allowed_actions"]


# ============================================================================
# Edge Cases and Special Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_unknown_resource_type_returns_empty():
    """Unknown resource type returns empty actions."""
    actions = await PermissionService.get_allowed_actions(
        user_id="user-123",
        resource_type="unknown_type",
        resource_id="resource-456",
    )

    assert actions == []


@pytest.mark.asyncio
async def test_metadata_with_string_json():
    """Handles metadata as JSON string correctly."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="owner",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="owner-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": '{"_x_oap_is_default": true}'},  # String JSON
        )

        assert "edit" not in actions
        assert "delete" not in actions


@pytest.mark.asyncio
async def test_admin_service_account_has_full_access():
    """Admin service accounts have full access like owners."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="admin",
    ):
        actions = await PermissionService.get_allowed_actions(
            user_id="service-account",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": {}},
        )

        assert "view" in actions
        assert "chat" in actions
        assert "edit" in actions
        assert "delete" in actions
        assert "share" in actions
        assert "manage_access" in actions


@pytest.mark.asyncio
async def test_malformed_metadata_json_handled_gracefully():
    """Malformed JSON metadata doesn't crash the service."""
    with patch(
        "langconnect.database.permissions.AssistantPermissionsManager.get_user_permission_for_assistant",
        return_value="owner",
    ):
        # Should not raise an exception
        actions = await PermissionService.get_allowed_actions(
            user_id="owner-123",
            resource_type="assistant",
            resource_id="assistant-456",
            resource_metadata={"metadata": '{"malformed": json}'},  # Invalid JSON
        )

        # Should default to treating as non-default (edit/delete allowed)
        assert "edit" in actions
        assert "delete" in actions
