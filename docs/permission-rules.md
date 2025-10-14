# Permission System Documentation

## Overview

The Agent OS Starter Kit uses a comprehensive permission system to control access to graphs (agent templates) and assistants (agent instances). This document serves as the single source of truth for understanding permission levels, capabilities, and enforcement.

**Security Model:**
- **Backend enforces all security** - All permission checks in the backend are actual security enforcement
- **Frontend checks are UI-only** - Frontend permission utilities control UI visibility but are NOT security enforcement
- **Service accounts have elevated access** - Can see and operate on all resources (with owner_id specification for operations)

---

## Permission Levels

### Graph Permissions

Graphs are agent templates (e.g., `deepagent`, `tools_agent`, `supervisor_agent`). Users need graph permissions to create assistants from templates.

| Level | Can View | Can Create Assistants | Can Manage Access |
|-------|----------|----------------------|-------------------|
| `access` | ✓ | ✓ | ✗ |
| `admin` | ✓ | ✓ | ✓ |

**Implementation:** `apps/langconnect/langconnect/database/permissions.py:148-168` (`GraphPermissionsManager.has_graph_permission`)

**Key Notes:**
- Graph permissions do NOT automatically grant assistant permissions
- Creating an assistant from a graph requires graph `access` or `admin` permission
- The creator becomes the `owner` of the new assistant
- `admin` users can grant/revoke graph permissions to other users

### Assistant Permissions

Assistants are configured agent instances. They inherit the graph_id of their template but have independent permissions.

| Level | Can View | Can Chat | Can Edit Config | Can Delete | Can Share |
|-------|----------|----------|-----------------|------------|-----------|
| `viewer` | ✓ | ✓ | ✗ | ✗ | ✗ |
| `editor` | ✓ | ✓ | ✓ | ✗ | ✗ |
| `owner` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `admin` (service only) | ✓ | ✓ | ✓ | ✓ | ✓ |

**Implementation:**
- Permission queries: `apps/langconnect/langconnect/database/permissions.py:379-390` (`AssistantPermissionsManager.get_user_permission_for_assistant`)
- Lifecycle operations: `apps/langconnect/langconnect/api/assistant_actions/lifecycle.py`

**Key Notes:**
- Assistant permissions are independent from graph permissions
- Permission hierarchy is NOT currently implemented (each level is boolean check)
- `owner` is the only level that can delete assistants
- `admin` is reserved for service accounts

---

## User Roles

Global user roles provide platform-wide capabilities beyond resource-specific permissions.

| Role | Description | Capabilities |
|------|-------------|--------------|
| `dev_admin` | Developer administrator | Full platform access, implicit graph admin (see note below) |
| `business_admin` | Business administrator | (Not currently implemented) |
| `user` | Standard user | Access based on explicit permissions only |

**Implementation:** `apps/langconnect/langconnect/database/permissions.py:113-119` (`GraphPermissionsManager.get_user_role`)

### Dev Admin Behavior (IMPORTANT)

**Inconsistency Alert:** Dev admin behavior differs between graphs and assistants:

1. **Graph Permissions:** Dev admins bypass ALL permission checks
   - Automatically have `admin` access to all graphs
   - No explicit permissions required
   - **Location:** `permissions.py:148-151` (returns True immediately for dev_admin)
   - **Location:** `permissions.py:189-202` (returns all graphs with admin level)

2. **Assistant Permissions:** Dev admins require EXPLICIT permissions
   - Must be granted `owner` permission to access assistants
   - No automatic bypass
   - **Location:** `permissions.py:379-390` (no dev_admin check)

**Design Decision Needed:**
This inconsistency is flagged in the technical debt. Team should decide:
- Option A: Add dev_admin bypass to assistant permissions (consistent with graphs)
- Option B: Remove dev_admin bypass from graph permissions (explicit is better)
- Option C: Document as intentional (graphs are templates, assistants are user data)

---

## Special Assistant Types

### User Default Assistants

**Identification:** `metadata._x_oap_is_default === true`

**Purpose:** Each user can have a default assistant per graph. This is the assistant that loads automatically when accessing a graph.

**Protection:**
- **Frontend:** Explicit checks prevent edit/delete (agent-utils.ts:150-160, 186-196)
- **Backend:** Implicit protection via system ownership (needs explicit check - see Phase 2)

**Current Limitation:** Backend does not explicitly validate default assistant status before modification. Protection relies on:
1. Convention: Default assistants have `owner_id = 'system'` or similar
2. Frontend checks preventing the action from reaching backend

**Recommendation:** Add explicit backend check (see Phase 2 implementation)

### Graph Template Assistants

**Identification:** `metadata.created_by === "system"`

**Purpose:** Automatically created by LangGraph to hold metadata and schemas for graph templates. Used for discovery and schema extraction.

**Behavior:**
- Filtered from user-facing lists in frontend
- Synced to `assistants_mirror` table for template lookups
- Not directly accessible via chat interface

### Primary Assistants

**Identification:** `metadata._x_oap_is_primary === true`

**Purpose:** Platform-wide primary assistant specified in deployment configuration (`NEXT_PUBLIC_DEPLOYMENTS`).

**Scope:** Only one primary assistant across all graphs and deployments.

---

## Permission Enforcement

### Frontend (UI-Only)

**File:** `apps/web/src/lib/agent-utils.ts`

**Functions:**
- `canUserDeleteAssistant(agent)` - Controls visibility of delete button
- `canUserEditAssistant(agent)` - Controls visibility of edit button
- `canUserRevokeOwnAccess(agent)` - Controls visibility of "Leave" button
- `canUserRevokeOwnGraphAccess(userRole, graphPermissionLevel)` - Controls graph access revocation
- `canUserSeeGraphActionMenu(graphPermissionLevel)` - Controls action menu visibility
- `canUserManageGraphAccess(graphPermissionLevel)` - Controls "Manage Access" button

**IMPORTANT:** These functions are **NOT security enforcement**. They only control UI element visibility for better UX. All security is enforced by backend endpoints.

### Backend (Security Enforcement)

**Files:**
- `apps/langconnect/langconnect/database/permissions.py` - Permission managers (580 lines)
- `apps/langconnect/langconnect/api/assistant_actions/lifecycle.py` - Assistant CRUD (848 lines)
- `apps/langconnect/langconnect/api/assistant_actions/permissions.py` - Assistant sharing (469 lines)
- `apps/langconnect/langconnect/api/graph_actions/permissions.py` - Graph permissions (528 lines)
- `apps/langconnect/langconnect/api/graph_actions/lifecycle.py` - Graph operations (1773 lines)

**Enforcement Points:**

1. **Assistant Creation** (`lifecycle.py:register_assistant`)
   - Requires graph `access` or `admin` permission
   - Creator becomes `owner` of new assistant
   - Location: `lifecycle.py:150-200` (approximate)

2. **Assistant Update** (`lifecycle.py:update_assistant`)
   - Requires `owner` or `editor` permission
   - **Missing:** Explicit check for default assistant (needs Phase 2)
   - Location: To be determined (need full file read)

3. **Assistant Deletion** (`lifecycle.py:delete_assistant`)
   - Requires `owner` permission
   - **Missing:** Explicit check for default assistant (needs Phase 2)
   - Location: To be determined (need full file read)

4. **Permission Granting** (`permissions.py:grant_assistant_permission`)
   - Requires `owner` permission on assistant
   - Creates notification for user-to-user sharing
   - Service accounts can grant directly without notification

5. **Permission Revocation** (`permissions.py:revoke_assistant_permission`)
   - Requires `owner` permission
   - Cannot revoke own `owner` permission (prevents orphaned assistants)

---

## Sharing Mechanisms

### User-to-User Sharing

**Flow:**
1. Owner calls share endpoint with target user ID and permission level
2. Backend creates notification record
3. Target user receives notification
4. Target user accepts notification
5. Backend grants permission

**Implementation:** `apps/langconnect/langconnect/api/assistant_actions/permissions.py`

**Rationale:** Prevents unwanted access grants, requires explicit user consent

### Service Account Sharing

**Flow:**
1. Service account calls grant permission endpoint
2. Backend grants permission directly (no notification)

**Rationale:** Service accounts are trusted automation, shouldn't require human acceptance

### Public Sharing

**Feature:** Assistants can be shared with all users via `system:public` granted_by value

**Implementation:** `apps/langconnect/langconnect/api/public_permissions.py`

**Mechanics:**
- Assistants marked public in `public_assistant_permissions` table
- When users access the platform, they receive permissions for all public assistants
- Public permissions can be revoked in two modes:
  - `revoke_all`: Removes permissions from all users immediately
  - `future_only`: Existing users keep access, new users don't receive it

---

## Permission Cascading

### Graph Permission Revocation

When a user's graph permission is revoked, their assistant permissions are automatically cascaded:

**Behavior:**
1. User loses graph `access` or `admin` permission
2. Database triggers fire (or application logic - needs verification)
3. User's permissions for ALL assistants in that graph are revoked
4. User can no longer create new assistants from that graph

**Implementation:** Needs investigation - likely database triggers

**Edge Case:** What happens to assistants the user owns? Are they:
- Deleted automatically?
- Reassigned to another owner?
- Kept with orphaned ownership?

**Action Required:** Investigate and document exact behavior

### Default Assistant Reassignment

When a user's default assistant is deleted:

**Behavior:**
1. Default assistant is deleted (or user loses access)
2. System automatically selects a new default assistant for that user/graph combination
3. New default is typically the most recently used or created assistant in that graph

**Implementation:** Database triggers in `supabase/volumes/` (likely)

**Rationale:** Ensures users always have a functional default when accessing a graph

---

## Edge Cases

### 1. Owner Can't Revoke Own Access

**Scenario:** User is owner of an assistant and tries to revoke their own owner permission

**Behavior:** Backend rejects the request

**Rationale:** Prevents orphaned assistants with no owner

**Workaround:** Owner should delete the assistant entirely or transfer ownership first

**Implementation:** `apps/langconnect/langconnect/api/assistant_actions/permissions.py` (revoke endpoint)

### 2. Dev Admin Can't Create Assistants

**Scenario:** Dev admin has implicit graph admin but hasn't created any assistants

**Behavior:** Dev admin can see all graphs but must explicitly create assistants like any user

**Rationale:** Assistant creation grants `owner` permission, which requires explicit action

**Note:** This is related to the dev_admin inconsistency mentioned above

### 3. Public Permission Future-Only Mode

**Scenario:** Assistant was public, owner revokes with `future_only` mode

**Behavior:**
- Existing users retain their permissions
- New users don't receive permission
- No notification sent to existing users
- Public flag is marked as revoked but permissions persist

**Use Case:** Soft deprecation without disrupting existing users

### 4. Service Account Must Specify Owner ID

**Scenario:** Service account creates an assistant

**Behavior:** Service account must provide `owner_id` parameter specifying the human user who should own the assistant

**Rationale:** Prevents service accounts from accumulating owned resources

**Implementation:** `lifecycle.py` (register_assistant endpoint)

### 5. Permission Hierarchy Not Enforced

**Scenario:** Code checks `permission_level === 'editor'` explicitly

**Current Behavior:** `owner` level users fail this check because comparison is exact match

**Expected Behavior:** `owner` should satisfy `editor` requirement (hierarchical)

**Status:** `PERMISSION_HIERARCHY` constant exists for collections but not used for assistants/graphs

**Recommendation:** Implement hierarchical permission checking in Phase 3

---

## Database Schema

### Tables

**Graph Permissions:**
```sql
langconnect.graph_permissions (
  graph_id TEXT,
  user_id TEXT,
  permission_level TEXT,  -- 'access' | 'admin'
  granted_by TEXT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  PRIMARY KEY (graph_id, user_id)
)
```

**Assistant Permissions:**
```sql
langconnect.assistant_permissions (
  id SERIAL PRIMARY KEY,
  assistant_id UUID,
  user_id TEXT,
  permission_level TEXT,  -- 'viewer' | 'editor' | 'owner' | 'admin'
  granted_by TEXT,        -- user_id | 'system' | 'system:public'
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  UNIQUE (assistant_id, user_id)
)
```

**Public Permissions:**
```sql
langconnect.public_assistant_permissions (
  id SERIAL PRIMARY KEY,
  assistant_id UUID,
  permission_level TEXT,
  created_by TEXT,
  created_at TIMESTAMP,
  revoked_at TIMESTAMP NULL,
  revoke_mode TEXT NULL,  -- 'revoke_all' | 'future_only'
  notes TEXT NULL
)
```

**User Roles:**
```sql
langconnect.user_roles (
  user_id TEXT PRIMARY KEY,
  role TEXT,              -- 'dev_admin' | 'business_admin' | 'user'
  email TEXT,
  display_name TEXT,
  created_at TIMESTAMP
)
```

---

## Testing Recommendations

### Frontend Permission Function Tests

Test that UI utilities correctly identify permission capabilities:

```typescript
describe('canUserDeleteAssistant', () => {
  it('should return false for default assistants even with owner permission', () => {
    const agent = { permission_level: 'owner', metadata: { _x_oap_is_default: true } };
    expect(canUserDeleteAssistant(agent)).toBe(false);
  });

  it('should return true for owner of custom assistant', () => {
    const agent = { permission_level: 'owner', metadata: {} };
    expect(canUserDeleteAssistant(agent)).toBe(true);
  });

  it('should return false for editor of custom assistant', () => {
    const agent = { permission_level: 'editor', metadata: {} };
    expect(canUserDeleteAssistant(agent)).toBe(false);
  });
});
```

### Backend Permission Enforcement Tests

Test that backend actually enforces security:

```python
@pytest.mark.asyncio
async def test_cannot_delete_default_assistant():
    """Verify backend rejects deletion of default assistants."""
    # Create default assistant
    assistant_id = await create_default_assistant(user_id="user123")

    # Attempt deletion as owner
    with pytest.raises(HTTPException) as exc:
        await delete_assistant(assistant_id=assistant_id, user_id="user123")

    assert exc.value.status_code == 400
    assert "default" in exc.value.detail.lower()

@pytest.mark.asyncio
async def test_dev_admin_graph_access():
    """Verify dev_admin has implicit graph access."""
    has_access = await GraphPermissionsManager.has_graph_permission(
        user_id="dev_admin_user",
        graph_id="deepagent",
        required_level="admin"
    )
    assert has_access == True

@pytest.mark.asyncio
async def test_editor_cannot_delete():
    """Verify editor cannot delete assistant."""
    # Grant editor permission
    await grant_permission(assistant_id="abc", user_id="user123", level="editor")

    # Attempt deletion
    with pytest.raises(HTTPException) as exc:
        await delete_assistant(assistant_id="abc", user_id="user123")

    assert exc.value.status_code == 403
```

---

## API Examples

### Check User Permission

```python
from langconnect.database.permissions import AssistantPermissionsManager

# Get user's permission level for an assistant
permission = await AssistantPermissionsManager.get_user_permission_for_assistant(
    user_id="user-123",
    assistant_id="assistant-456"
)
# Returns: 'owner' | 'editor' | 'viewer' | None
```

### Grant Permission

```python
from langconnect.database.permissions import AssistantPermissionsManager

# Grant permission to another user
success = await AssistantPermissionsManager.grant_assistant_permission(
    assistant_id="assistant-456",
    user_id="user-789",
    permission_level="editor",
    granted_by="user-123"  # Current user ID
)
```

### Check Graph Permission

```python
from langconnect.database.permissions import GraphPermissionsManager

# Check if user can create assistants from a graph
has_access = await GraphPermissionsManager.has_graph_permission(
    user_id="user-123",
    graph_id="deepagent",
    required_level="access"
)
# Returns: True | False
```

---

## Future Improvements

### Phase 3: Centralized Permission Service

Create a single service that returns allowed actions:

```python
from langconnect.services.permission_service import PermissionService

allowed_actions = await PermissionService.get_allowed_actions(
    user_id="user-123",
    resource_type="assistant",
    resource_id="assistant-456"
)
# Returns: ['view', 'edit', 'chat', 'share'] based on permissions
```

This would:
- Centralize all permission logic in one place
- Enable backend-driven UI permissions (Phase 4)
- Reduce frontend/backend logic duplication
- Make permission rules easier to audit and modify

### Phase 4: Backend-Driven Permissions

Update API responses to include `allowed_actions`:

```json
{
  "assistant_id": "abc-123",
  "name": "My Assistant",
  "permission_level": "editor",
  "allowed_actions": ["view", "edit", "chat"]
}
```

This would:
- Remove need for frontend permission logic
- Prevent frontend/backend permission contradictions
- Enable dynamic permission rules without frontend changes
- Improve security by centralizing all logic

---

## Related Files

### Backend Files
- `apps/langconnect/langconnect/database/permissions.py` - Permission managers (580 lines)
- `apps/langconnect/langconnect/api/assistant_actions/lifecycle.py` - Assistant CRUD
- `apps/langconnect/langconnect/api/assistant_actions/permissions.py` - Assistant sharing
- `apps/langconnect/langconnect/api/graph_actions/permissions.py` - Graph permissions
- `apps/langconnect/langconnect/api/graph_actions/lifecycle.py` - Graph operations
- `apps/langconnect/langconnect/api/public_permissions.py` - Public sharing

### Frontend Files
- `apps/web/src/lib/agent-utils.ts` - Permission utility functions (325 lines)
- Components using permissions (7+ files in `apps/web/src/features/`)

### Database Files
- `database/migrate.py` - Migration script
- `supabase/volumes/*.sql` - Initial schema and triggers

---

## Glossary

- **Graph**: Agent template (e.g., `deepagent`, `tools_agent`)
- **Assistant**: Configured agent instance created from a graph
- **Permission Level**: Access level for a specific resource (graph or assistant)
- **User Role**: Platform-wide capability (e.g., `dev_admin`)
- **Default Assistant**: User's preferred assistant for a graph (one per user per graph)
- **Primary Assistant**: Platform-wide default assistant specified in deployment config
- **Template Assistant**: System-created assistant holding graph metadata
- **Service Account**: Automated actor with elevated privileges
- **Cascading**: Automatic permission changes triggered by parent permission changes

---

## Version History

- **2025-10-13**: Initial documentation (Phase 1 implementation)
