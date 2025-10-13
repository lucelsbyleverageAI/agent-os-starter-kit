"""
Agent collaboration models for graph and assistant management.
"""

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum
from uuid import UUID


# ==================== GRAPH SCAN MODELS ====================

class GraphScanItem(BaseModel):
    """Individual graph discovered during scan."""
    graph_id: str = Field(..., description="Graph identifier (e.g., 'tools_agent')")
    schema_accessible: bool = Field(..., description="Whether schema endpoint is accessible")
    assistants_count: int = Field(..., description="Number of assistants created from this graph")
    has_default_assistant: bool = Field(..., description="Whether a default assistant exists")
    needs_initialization: bool = Field(..., description="Whether graph needs initialization")
    needs_enhancement: Optional[bool] = Field(None, description="Whether system assistants need enhancement with proper metadata and names")
    needs_system_enhancement: Optional[bool] = Field(None, description="Whether system assistants need metadata enhancement (Scenario 1)")
    needs_user_inheritance: Optional[bool] = Field(None, description="Whether current user needs permission inheritance (Scenario 2)")  
    needs_dev_admin_sync: Optional[bool] = Field(None, description="Whether dev_admin needs permission sync (Scenario 3)")
    user_permission_level: Optional[str] = Field(None, description="Current user's permission level for this graph (admin/access)")
    error: Optional[str] = Field(None, description="Error message if graph is invalid")
    cleanup_required: Optional[bool] = Field(None, description="Whether cleanup is needed")


class GraphScanMetadata(BaseModel):
    """Metadata about the scan operation."""
    langgraph_graphs_found: int = Field(..., description="Total graphs found in LangGraph")
    valid_graphs: int = Field(..., description="Number of valid, accessible graphs")
    invalid_graphs: int = Field(..., description="Number of invalid or inaccessible graphs")
    scan_duration_ms: int = Field(..., description="Time taken for scan in milliseconds")


class GraphScanResponse(BaseModel):
    """Response from graph discovery scan."""
    valid_graphs: List[GraphScanItem] = Field(default_factory=list, description="Valid, accessible graphs")
    invalid_graphs: List[GraphScanItem] = Field(default_factory=list, description="Invalid or inaccessible graphs")
    scan_metadata: GraphScanMetadata = Field(..., description="Scan operation metadata")


# ==================== PERMISSION MODELS ====================

class GraphPermissionLevel(str, Enum):
    """Graph permission levels."""
    ADMIN = "admin"
    ACCESS = "access"


class AssistantPermissionLevel(str, Enum):
    """Assistant permission levels."""
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


# ==================== GRAPH INITIALIZATION MODELS ====================

class GraphInitializeRequest(BaseModel):
    """Request model for initializing a new graph."""
    assistant_name: Optional[str] = Field(None, description="Override name for default assistant")
    grant_dev_admin_access: bool = Field(True, description="Grant dev_admin role automatic access")
    reason: Optional[str] = Field(None, description="Reason for initialization (for audit log)")


class PermissionCreated(BaseModel):
    """Individual permission that was created during initialization."""
    user_role: str = Field(..., description="Role that received permission")
    graph_permission: str = Field(..., description="Permission level granted for graph")
    assistant_permission: str = Field(..., description="Permission level granted for assistant")


class GraphInitializeResponse(BaseModel):
    """Response from graph initialization."""
    graph_id: str = Field(..., description="Graph identifier that was initialized")
    assistant_id: str = Field(..., description="Default assistant ID created in LangGraph")
    assistant_name: str = Field(..., description="Name of the default assistant")
    permissions_created: List[PermissionCreated] = Field(default_factory=list, description="Permissions created during initialization")
    created_at: str = Field(..., description="ISO timestamp of initialization")


# ==================== GRAPH CLEANUP MODELS ====================

class DeletedAssistant(BaseModel):
    """Assistant that was deleted during cleanup."""
    assistant_id: str = Field(..., description="Assistant ID that was deleted")
    graph_id: str = Field(..., description="Graph this assistant belonged to")
    name: str = Field(..., description="Assistant name")


class CleanupSummary(BaseModel):
    """Summary of cleanup operations performed."""
    total_operations: int = Field(..., description="Total cleanup operations attempted")
    successful: int = Field(..., description="Number of successful operations")
    failed: int = Field(..., description="Number of failed operations")


class PermissionCleanup(BaseModel):
    """Permission cleanup statistics."""
    graph_permissions_removed: int = Field(..., description="Graph permissions removed")
    assistant_permissions_removed: int = Field(..., description="Assistant permissions removed")


class GraphCleanupRequest(BaseModel):
    """Request model for graph cleanup operations."""
    target_graphs: Optional[List[str]] = Field(None, description="Specific graphs to clean up (if not provided, cleans all invalid graphs)")
    dry_run: bool = Field(False, description="Preview operations without making changes")
    confirm_deletion: bool = Field(False, description="Required confirmation for actual deletion")


class GraphCleanupResponse(BaseModel):
    """Response from graph cleanup operations."""
    deleted_graphs: List[str] = Field(default_factory=list, description="Graph IDs that were cleaned up")
    deleted_assistants: List[DeletedAssistant] = Field(default_factory=list, description="Assistants that were deleted")
    permissions_cleaned: PermissionCleanup = Field(..., description="Permission cleanup statistics")
    cleanup_summary: CleanupSummary = Field(..., description="Overall cleanup summary")
    dry_run: bool = Field(..., description="Whether this was a dry run")
    warnings: List[str] = Field(default_factory=list, description="Warnings about cleanup operations")


# ==================== GRAPH PERMISSION MANAGEMENT MODELS ====================

class GraphInfo(BaseModel):
    """Basic graph information for listing."""
    graph_id: str = Field(..., description="Graph identifier")
    schema_accessible: bool = Field(..., description="Whether schema is accessible")
    assistants_count: int = Field(..., description="Number of assistants in this graph")
    has_default_assistant: bool = Field(..., description="Whether default assistant exists")
    user_permission_level: Optional[str] = Field(None, description="User's permission level for this graph")
    created_at: Optional[str] = Field(None, description="When user gained access to this graph")
    allowed_actions: Optional[List[str]] = Field(None, description="Actions user can perform (view, create_assistant, manage_access, revoke_own) - Phase 3 centralized permissions")


class GraphListResponse(BaseModel):
    """Response for listing accessible graphs."""
    graphs: List[GraphInfo] = Field(default_factory=list, description="Graphs accessible to the user")
    total_count: int = Field(..., description="Total number of accessible graphs")


class UserPermissionInfo(BaseModel):
    """User permission information for a graph."""
    user_id: str = Field(..., description="User identifier")
    email: str = Field(..., description="User email")
    display_name: str = Field(..., description="User display name")
    permission_level: str = Field(..., description="Permission level (admin/access)")
    granted_by: str = Field(..., description="Who granted this permission")
    granted_at: str = Field(..., description="When permission was granted")


class GraphPermissionsResponse(BaseModel):
    """Response for getting graph permissions."""
    graph_id: str = Field(..., description="Graph identifier")
    permissions: List[UserPermissionInfo] = Field(default_factory=list, description="List of user permissions")
    total_users: int = Field(..., description="Total number of users with access")


class GrantGraphAccessRequest(BaseModel):
    """Request to grant graph access to users."""
    users: List[Dict[str, str]] = Field(..., description="List of users to grant access to")
    # Each user should have: {"user_id": "uuid", "level": "admin|access"}
    notify_users: bool = Field(False, description="Whether to notify users of access granted")
    reason: Optional[str] = Field(None, description="Reason for granting access (for audit log)")


class GrantedPermission(BaseModel):
    """Individual permission that was granted."""
    user_id: str = Field(..., description="User who received permission")
    email: str = Field(..., description="User email")
    permission_level: str = Field(..., description="Permission level granted")
    was_updated: bool = Field(..., description="Whether this was an update to existing permission")


class GrantGraphAccessResponse(BaseModel):
    """Response from granting graph access."""
    graph_id: str = Field(..., description="Graph that was accessed")
    permissions_granted: List[GrantedPermission] = Field(default_factory=list, description="Permissions that were granted directly (service accounts)")
    notifications_created: List[Dict[str, Any]] = Field(default_factory=list, description="Notifications created for user-to-user sharing")
    successful_grants: int = Field(..., description="Number of successful grants (direct grants + notifications)")
    failed_grants: int = Field(..., description="Number of failed permission grants")
    errors: List[str] = Field(default_factory=list, description="Any errors that occurred")


class RevokeGraphAccessResponse(BaseModel):
    """Response from revoking graph access."""
    graph_id: str = Field(..., description="Graph that access was revoked from")
    user_id: str = Field(..., description="User whose access was revoked")
    revoked: bool = Field(..., description="Whether access was successfully revoked")
    message: str = Field(..., description="Result message")


# ==================== ASSISTANT LIFECYCLE MODELS ====================

class AssistantInfo(BaseModel):
    """Assistant information for listing."""
    assistant_id: str = Field(..., description="Assistant identifier")
    graph_id: str = Field(..., description="Graph this assistant belongs to")
    name: str = Field(..., description="Assistant name")
    description: Optional[str] = Field(None, description="Assistant description")
    permission_level: str = Field(..., description="User's permission level (owner/user)")
    owner_id: str = Field(..., description="Assistant owner ID")
    owner_display_name: Optional[str] = Field(None, description="Assistant owner display name")
    created_at: str = Field(..., description="When assistant was created")
    updated_at: Optional[str] = Field(None, description="When assistant was last updated")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Assistant metadata from LangGraph")
    allowed_actions: Optional[List[str]] = Field(None, description="Actions user can perform (view, chat, edit, delete, share) - Phase 3 centralized permissions")


class AssistantListResponse(BaseModel):
    """Response for listing accessible assistants."""
    assistants: List[AssistantInfo] = Field(default_factory=list, description="Assistants accessible to the user")
    total_count: int = Field(..., description="Total number of accessible assistants")
    owned_count: int = Field(..., description="Number of assistants owned by the user")
    shared_count: int = Field(..., description="Number of assistants shared with the user")


class AssistantRegistrationRequest(BaseModel):
    """Request to register an assistant after LangGraph creation."""
    assistant_id: str = Field(..., description="LangGraph assistant ID to register")
    name: Optional[str] = Field(None, description="Override display name (uses LangGraph name if not provided)")
    description: Optional[str] = Field(None, description="Assistant description")
    config: Optional[Dict[str, Any]] = Field(None, description="Assistant configuration for future reference")
    owner_id: Optional[str] = Field(None, description="Owner ID (required for service accounts)")
    share_with: Optional[List[Dict[str, str]]] = Field(None, description="Users to share with upon registration")
    reason: Optional[str] = Field(None, description="Reason for registration (for audit log)")


class AssistantPermissionInfo(BaseModel):
    """Permission information for an assistant."""
    user_id: str = Field(..., description="User identifier")
    email: str = Field(..., description="User email")
    display_name: str = Field(..., description="User display name")
    permission_level: str = Field(..., description="Permission level (owner/editor/viewer)")
    granted_by: str = Field(..., description="Who granted this permission")
    granted_at: str = Field(..., description="When permission was granted")


class AssistantDetailsResponse(BaseModel):
    """Response for getting assistant details."""
    assistant_id: str = Field(..., description="Assistant identifier")
    graph_id: str = Field(..., description="Graph this assistant belongs to")
    name: str = Field(..., description="Assistant name")
    description: Optional[str] = Field(None, description="Assistant description")
    owner_id: str = Field(..., description="Assistant owner ID")
    owner_display_name: Optional[str] = Field(None, description="Assistant owner display name")
    created_at: str = Field(..., description="When assistant was created")
    updated_at: Optional[str] = Field(None, description="When assistant was last updated")
    user_permission_level: str = Field(..., description="Current user's permission level")
    permissions: List[AssistantPermissionInfo] = Field(default_factory=list, description="All user permissions (owner only)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Assistant metadata from LangGraph")
    config: Optional[Dict[str, Any]] = Field(None, description="Assistant configuration from LangGraph")
    schemas_warming: Optional[bool] = Field(False, description="Whether schemas are still being cached (true means schemas may not be immediately available)")
    allowed_actions: Optional[List[str]] = Field(None, description="Actions user can perform (view, chat, edit, delete, share, manage_access) - Phase 3 centralized permissions")


class AssistantUpdateRequest(BaseModel):
    """Request to update an assistant."""
    name: Optional[str] = Field(None, description="New assistant name")
    description: Optional[str] = Field(None, description="New assistant description")
    config: Optional[Dict[str, Any]] = Field(None, description="New assistant configuration")
    reason: Optional[str] = Field(None, description="Reason for update (for audit log)")


class AssistantUpdateResponse(BaseModel):
    """Response from updating an assistant."""
    assistant_id: str = Field(..., description="Assistant that was updated")
    updated_fields: List[str] = Field(default_factory=list, description="Fields that were updated")
    success: bool = Field(..., description="Whether update was successful")
    message: str = Field(..., description="Result message")


class AssistantDeleteResponse(BaseModel):
    """Response from deleting an assistant."""
    assistant_id: str = Field(..., description="Assistant that was deleted")
    deleted_from_langgraph: bool = Field(..., description="Whether assistant was deleted from LangGraph")
    permissions_cleaned: int = Field(..., description="Number of permissions cleaned up")
    success: bool = Field(..., description="Whether deletion was successful")
    message: str = Field(..., description="Result message")


# ==================== ASSISTANT SHARING MODELS ====================

class ShareAssistantUser(BaseModel):
    """User to share assistant with."""
    user_id: str = Field(..., description="User ID to share with")
    permission_level: str = Field("user", description="Permission level to grant (user)")


class ShareAssistantRequest(BaseModel):
    """Request to share an assistant with users."""
    users: List[ShareAssistantUser] = Field(..., description="Users to share assistant with")
    notify_users: bool = Field(False, description="Whether to notify users of shared access")
    reason: Optional[str] = Field(None, description="Reason for sharing (for audit log)")


class SharedUser(BaseModel):
    """User who was granted assistant access."""
    user_id: str = Field(..., description="User who received access")
    email: str = Field(..., description="User email")
    display_name: str = Field(..., description="User display name")
    permission_level: str = Field(..., description="Permission level granted")
    was_updated: bool = Field(..., description="Whether this was an update to existing permission")


class ShareAssistantResponse(BaseModel):
    """Response from sharing an assistant."""
    assistant_id: str = Field(..., description="Assistant that was shared")
    users_shared: List[SharedUser] = Field(default_factory=list, description="Users who were granted direct access (service accounts)")
    notifications_created: List[Dict[str, Any]] = Field(default_factory=list, description="Notifications created for user-to-user sharing")
    successful_shares: int = Field(..., description="Number of successful shares (direct grants + notifications)")
    failed_shares: int = Field(..., description="Number of failed shares")
    errors: List[str] = Field(default_factory=list, description="Any errors that occurred")


class RevokeAssistantAccessResponse(BaseModel):
    """Response from revoking assistant access."""
    assistant_id: str = Field(..., description="Assistant that access was revoked from")
    user_id: str = Field(..., description="User whose access was revoked")
    revoked: bool = Field(..., description="Whether access was successfully revoked")
    message: str = Field(..., description="Result message")


class AssistantPermissionsResponse(BaseModel):
    """Response for getting assistant permissions (sharing details)."""
    assistant_id: str = Field(..., description="Assistant identifier")
    assistant_name: str = Field(..., description="Assistant name")
    owner_id: str = Field(..., description="Assistant owner ID")
    owner_display_name: Optional[str] = Field(None, description="Assistant owner display name")
    permissions: List[AssistantPermissionInfo] = Field(default_factory=list, description="List of user permissions")
    total_users: int = Field(..., description="Total number of users with access")
    shared_users: int = Field(..., description="Number of users with shared access (excluding owner)")


# ==================== NOTIFICATION MODELS ====================

class NotificationStatus(str, Enum):
    """Notification status values."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class NotificationType(str, Enum):
    """Notification type values."""
    GRAPH_SHARE = "graph_share"
    ASSISTANT_SHARE = "assistant_share"
    COLLECTION_SHARE = "collection_share"


class NotificationInfo(BaseModel):
    """Individual notification information."""
    id: str = Field(..., description="Notification identifier")
    recipient_user_id: str = Field(..., description="User who receives the notification")
    type: NotificationType = Field(..., description="Type of notification")
    resource_id: str = Field(..., description="ID of the resource being shared")
    resource_type: str = Field(..., description="Type of resource (graph, assistant, collection)")
    permission_level: str = Field(..., description="Permission level being offered")
    sender_user_id: str = Field(..., description="User who initiated the sharing")
    sender_display_name: Optional[str] = Field(None, description="Display name of the sender")
    status: NotificationStatus = Field(..., description="Current notification status")
    created_at: str = Field(..., description="When notification was created")
    updated_at: str = Field(..., description="When notification was last updated")
    responded_at: Optional[str] = Field(None, description="When user responded to notification")
    expires_at: str = Field(..., description="When notification expires")
    resource_name: str = Field(..., description="Name of the resource (snapshot)")
    resource_description: Optional[str] = Field(None, description="Description of the resource")
    
    @field_validator('id', 'recipient_user_id', 'sender_user_id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v: Union[str, UUID]) -> str:
        """Convert UUID objects to strings for database compatibility."""
        if isinstance(v, UUID):
            return str(v)
        return v


class NotificationsListResponse(BaseModel):
    """Response for listing user notifications."""
    notifications: List[NotificationInfo] = Field(default_factory=list, description="List of notifications")
    total_count: int = Field(..., description="Total number of notifications")
    pending_count: int = Field(..., description="Number of pending notifications")


class NotificationUnreadCountResponse(BaseModel):
    """Response for getting unread notification count."""
    unread_count: int = Field(..., description="Number of unread (pending) notifications")


class NotificationActionRequest(BaseModel):
    """Request to accept or reject a notification."""
    reason: Optional[str] = Field(None, description="Reason for action (for audit log)")


class NotificationActionResponse(BaseModel):
    """Response from accepting or rejecting a notification."""
    notification_id: str = Field(..., description="Notification that was acted upon")
    action: str = Field(..., description="Action taken (accepted/rejected)")
    success: bool = Field(..., description="Whether action was successful")
    message: str = Field(..., description="Result message")
    permission_granted: Optional[bool] = Field(None, description="Whether permission was granted (for accepts)")
    # Optional guidance fields for UX orchestration
    next_action: Optional[str] = Field(None, description="Suggested next action for the client (e.g., 'accept_graph')")
    requires_graph_first: Optional[bool] = Field(None, description="Whether a graph permission must be accepted before this one")
    related_graph_notification_id: Optional[str] = Field(None, description="Pending graph notification related to this assistant invite, if any")


# ==================== ADMIN PLATFORM INITIALIZATION MODELS ====================

class AdminInitializePlatformRequest(BaseModel):
    """Request model for admin platform initialization."""
    dry_run: bool = Field(False, description="Preview operations without making changes")
    target_user_id: Optional[str] = Field(None, description="Target specific user for inheritance (optional)")
    reason: Optional[str] = Field(None, description="Reason for initialization (for audit log)")


class EnhancementResult(BaseModel):
    """Result from a single enhancement operation."""
    operation: str = Field(..., description="Type of enhancement performed")
    success: bool = Field(..., description="Whether operation was successful")
    total_enhanced: int = Field(..., description="Number of items enhanced")
    failed: int = Field(0, description="Number of failed enhancements")
    message: str = Field(..., description="Result message")
    errors: List[str] = Field(default_factory=list, description="Any errors that occurred")


class AdminInitializePlatformResponse(BaseModel):
    """Response from admin platform initialization."""
    dry_run: bool = Field(..., description="Whether this was a dry run")
    operations_performed: List[EnhancementResult] = Field(default_factory=list, description="Enhancement operations performed")
    total_operations: int = Field(..., description="Total number of operations performed")
    successful_operations: int = Field(..., description="Number of successful operations")
    failed_operations: int = Field(..., description="Number of failed operations")
    duration_ms: int = Field(..., description="Total operation duration in milliseconds")
    warnings: List[str] = Field(default_factory=list, description="Warnings about operations")
    summary: str = Field(..., description="Summary of all operations performed")
