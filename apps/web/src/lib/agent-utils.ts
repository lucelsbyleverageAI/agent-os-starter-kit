import { Agent, GraphInfo } from "@/types/agent";
import { getDeployments } from "./environment/deployments";
import { Assistant } from "@langchain/langgraph-sdk";

/**
 * Determines if an agent is a user default assistant.
 *
 * User default assistants are created by users or the system on behalf of users,
 * and marked as the default agent for a specific graph. Each user can have their
 * own default assistant per graph. This is NOT the primary agent for the entire
 * platform, but rather the default agent for a given graph.
 *
 * @param agent The agent to check
 * @returns True if the agent is a user default assistant (_x_oap_is_default === true)
 */
export function isUserDefaultAssistant(
  agent: Agent | Assistant,
): boolean {
  const raw = (agent as any)?.metadata;
  let md: any = raw;
  if (typeof raw === 'string') {
    try { md = JSON.parse(raw); } catch { md = {}; }
  }
  const flag = md?._x_oap_is_default;
  return flag === true || flag === 'true' || flag === 1;
}

/**
 * Determines if an agent is a graph template assistant.
 *
 * Graph template assistants are created automatically by LangGraph to hold
 * metadata and schemas for each graph template. They serve as the source of
 * truth for graph configuration and are used for discovery and schema extraction.
 *
 * These assistants are filtered from user-facing lists but are synced to the
 * mirror for template lookups. They are identified by metadata.created_by === "system".
 *
 * @param agent The agent to check
 * @returns True if the agent is a graph template assistant (created_by === "system")
 */
export function isGraphTemplateAssistant(
  agent: Agent | Assistant,
): boolean {
  return agent.metadata?.created_by === "system";
}

/**
 * Determines if an agent is the primary assistant for a graph.
 *
 * A primary assistant is the default assistant for all graphs provided
 * to OAP. This can only be one agent, across all graphs & deployments,
 * and is specified by setting `isDefault: true` and `defaultGraphId`
 * on a deployment in the `NEXT_PUBLIC_DEPLOYMENTS` environment variable.
 *
 * @param agent The agent to check
 * @returns True if the agent is the primary assistant for a graph
 */
export function isPrimaryAssistant(agent: Agent | Assistant): boolean {
  const raw = (agent as any)?.metadata;
  let md: any = raw;
  if (typeof raw === 'string') {
    try { md = JSON.parse(raw); } catch { md = {}; }
  }
  const flag = md?._x_oap_is_primary;
  return flag === true || flag === 'true' || flag === 1;
}

export function isUserSpecifiedDefaultAgent(agent: Agent): boolean {
  const deployments = getDeployments();
  const defaultDeployment = deployments.find((d) => d.isDefault);
  if (!defaultDeployment) {
    return false;
  }
  return (
    isUserDefaultAssistant(agent) &&
    agent.graph_id === defaultDeployment.defaultGraphId &&
    agent.deploymentId === defaultDeployment.id
  );
}

/**
 * Sorts an array of agents within a group.
 * The default agent comes first, followed by others sorted by `updated_at` descending.
 * @param agentGroup An array of agents belonging to the same group.
 * @returns A new array with the sorted agents.
 */
export function sortAgentGroup(agentGroup: Agent[]): Agent[] {
  return [...agentGroup].sort((a, b) => {
    const aIsDefault = isUserDefaultAssistant(a);
    const bIsDefault = isUserDefaultAssistant(b);

    if (aIsDefault && !bIsDefault) {
      return -1; // a comes first
    }
    if (!aIsDefault && bIsDefault) {
      return 1; // b comes first
    }

    // If both are default or both are not, sort by updated_at descending
    // Handle potential missing or invalid dates gracefully
    const timeA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
    const timeB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
    const validTimeA = !isNaN(timeA) ? timeA : 0;
    const validTimeB = !isNaN(timeB) ? timeB : 0;

    return validTimeB - validTimeA; // Newest first
  });
}

/**
 * Groups an array of agents by their `graph_id`.
 * @param agents An array of agents.
 * @returns An array of arrays, where each inner array contains agents belonging to the same graph.
 */
export function groupAgentsByGraphs<AgentOrAssistant extends Agent | Assistant>(
  agents: AgentOrAssistant[],
): AgentOrAssistant[][] {
  return Object.values(
    agents.reduce<Record<string, AgentOrAssistant[]>>((acc, agent) => {
      const groupId = agent.graph_id;
      if (!acc[groupId]) {
        acc[groupId] = [];
      }
      acc[groupId].push(agent);
      return acc;
    }, {}),
  );
}

/**
 * **UI-ONLY CHECK:** Determines if a user can delete an assistant based on backend permissions.
 *
 * **IMPORTANT:** This function is NOT security enforcement. It only controls UI element
 * visibility (delete button). Actual security is enforced by backend endpoints.
 * See: `apps/langconnect/langconnect/api/assistant_actions/lifecycle.py`
 *
 * **Phase 4 Complete:** This function now relies entirely on backend-provided `allowed_actions`.
 * The backend PermissionService handles all permission logic including:
 * - Default assistant protection (cannot delete system-managed assistants)
 * - Owner-only deletion rights
 * - Editor/viewer restrictions
 *
 * @param agent The agent to check (must have allowed_actions field)
 * @returns True if the user can delete this assistant
 * @throws Error if allowed_actions is missing (indicates API integration issue)
 * @example
 * // Backend says user can delete
 * canUserDeleteAssistant({ allowed_actions: ['view', 'chat', 'delete'] }) // true
 *
 * // Backend says user cannot delete
 * canUserDeleteAssistant({ allowed_actions: ['view', 'chat', 'edit'] }) // false
 */
export function canUserDeleteAssistant(agent: Agent): boolean {
  if (!agent.allowed_actions) {
    throw new Error(
      'canUserDeleteAssistant: allowed_actions is missing from agent. ' +
      'This indicates the backend API is not returning permission data correctly. ' +
      'Check that all API endpoints include allowed_actions in their responses.'
    );
  }

  return agent.allowed_actions.includes('delete');
}

/**
 * **UI-ONLY CHECK:** Determines if a user can edit an assistant based on backend permissions.
 *
 * **IMPORTANT:** This function is NOT security enforcement. It only controls UI element
 * visibility (edit button). Actual security is enforced by backend endpoints.
 * See: `apps/langconnect/langconnect/api/assistant_actions/lifecycle.py`
 *
 * **Phase 4 Complete:** This function now relies entirely on backend-provided `allowed_actions`.
 * The backend PermissionService handles all permission logic including:
 * - Default assistant protection (cannot edit system-managed assistants)
 * - Owner and editor edit rights
 * - Viewer restrictions
 *
 * @param agent The agent to check (must have allowed_actions field)
 * @returns True if the user can edit this assistant
 * @throws Error if allowed_actions is missing (indicates API integration issue)
 * @example
 * // Backend says user can edit
 * canUserEditAssistant({ allowed_actions: ['view', 'chat', 'edit'] }) // true
 *
 * // Backend says user cannot edit
 * canUserEditAssistant({ allowed_actions: ['view', 'chat'] }) // false
 */
export function canUserEditAssistant(agent: Agent): boolean {
  if (!agent.allowed_actions) {
    throw new Error(
      'canUserEditAssistant: allowed_actions is missing from agent. ' +
      'This indicates the backend API is not returning permission data correctly. ' +
      'Check that all API endpoints include allowed_actions in their responses.'
    );
  }

  return agent.allowed_actions.includes('edit');
}

/**
 * **UI-ONLY CHECK:** Determines if a user can revoke their own access to an assistant.
 *
 * **IMPORTANT:** This function is NOT security enforcement. It only controls UI element
 * visibility ("Leave" button). Actual security is enforced by backend endpoints.
 * See: `apps/langconnect/langconnect/api/assistant_actions/permissions.py`
 *
 * **Phase 4 Complete:** This function now relies entirely on backend-provided `allowed_actions`.
 * The backend PermissionService handles all permission logic including:
 * - Editors and viewers can leave shared assistants
 * - Owners cannot leave (they should delete the assistant instead)
 * - Default assistants are protected from revocation
 *
 * **Implementation Note:** For assistants, we infer revocation ability by checking:
 * - User must NOT have 'manage_access' permission (owners have this)
 * - User must NOT be the owner (double-check with permission_level)
 *
 * @param agent The agent to check (must have allowed_actions field)
 * @returns True if the user can revoke their own access to this assistant
 * @throws Error if allowed_actions is missing (indicates API integration issue)
 * @example
 * // Editor can leave (no manage_access, not owner)
 * canUserRevokeOwnAccess({
 *   allowed_actions: ['view', 'chat', 'edit'],
 *   permission_level: 'editor'
 * }) // true
 *
 * // Owner cannot leave (has manage_access)
 * canUserRevokeOwnAccess({
 *   allowed_actions: ['view', 'chat', 'edit', 'delete', 'manage_access'],
 *   permission_level: 'owner'
 * }) // false
 */
export function canUserRevokeOwnAccess(agent: Agent): boolean {
  if (!agent.allowed_actions) {
    throw new Error(
      'canUserRevokeOwnAccess: allowed_actions is missing from agent. ' +
      'This indicates the backend API is not returning permission data correctly. ' +
      'Check that all API endpoints include allowed_actions in their responses.'
    );
  }

  // For assistants, non-owners can revoke own access (no explicit action needed)
  // This is inferred: if user has manage_access, they're owner and can't revoke self
  const canManage = agent.allowed_actions.includes('manage_access');
  const isOwner = agent.permission_level === 'owner';

  // Non-owners (editors/viewers) can leave
  return !isOwner && !canManage;
}

/**
 * **UI-ONLY CHECK:** Determines if a user can revoke their own access to a graph.
 *
 * **IMPORTANT:** This function is NOT security enforcement. It only controls UI element
 * visibility ("Leave" button for graphs). Actual security is enforced by backend endpoints.
 * See: `apps/langconnect/langconnect/api/graph_actions/permissions.py`
 *
 * **Phase 4 Complete:** This function now relies entirely on backend-provided `allowed_actions`.
 * The backend PermissionService handles all permission logic including:
 * - Regular users with access/admin can revoke their own access
 * - dev_admin users cannot revoke (system protection)
 * - Users without permission cannot revoke (nothing to revoke)
 *
 * @param userRole The user's global role (deprecated parameter, not used anymore)
 * @param graphPermissionLevel The user's permission level (deprecated parameter, not used anymore)
 * @param graph The graph object with allowed_actions (REQUIRED)
 * @returns True if the user can revoke their own access to this graph
 * @throws Error if graph or allowed_actions is missing (indicates API integration issue)
 * @example
 * // Regular user can revoke (backend provides revoke_own action)
 * canUserRevokeOwnGraphAccess('user', 'access', { allowed_actions: ['view', 'create_assistant', 'revoke_own'] }) // true
 *
 * // Dev admin cannot revoke (backend omits revoke_own action for system protection)
 * canUserRevokeOwnGraphAccess('dev_admin', 'admin', { allowed_actions: ['view', 'create_assistant', 'manage_access'] }) // false
 */
export function canUserRevokeOwnGraphAccess(
  userRole: string | null | undefined,
  graphPermissionLevel: 'admin' | 'access' | null | undefined,
  graph?: GraphInfo
): boolean {
  if (!graph || !graph.allowed_actions) {
    throw new Error(
      'canUserRevokeOwnGraphAccess: graph or allowed_actions is missing. ' +
      'This indicates the backend API is not returning permission data correctly. ' +
      'Check that all graph API endpoints include allowed_actions in their responses.'
    );
  }

  return graph.allowed_actions.includes('revoke_own');
}

/**
 * **UI-ONLY CHECK:** Determines if a user should see the graph action menu.
 *
 * **IMPORTANT:** This function is NOT security enforcement. It only controls UI element
 * visibility (action menu/dropdown). Actual security is enforced by backend endpoints.
 *
 * **Phase 4 Complete:** This function now relies entirely on backend-provided `allowed_actions`.
 * The action menu should be visible if the user has any meaningful actions beyond just viewing:
 * - Manage access (admin feature)
 * - Revoke own access (leave the graph)
 *
 * @param graphPermissionLevel The user's permission level (deprecated parameter, not used anymore)
 * @param graph The graph object with allowed_actions (REQUIRED)
 * @returns True if the user should see the graph action menu
 * @throws Error if graph or allowed_actions is missing (indicates API integration issue)
 * @example
 * // User with actions - show menu
 * canUserSeeGraphActionMenu('admin', { allowed_actions: ['view', 'manage_access', 'revoke_own'] }) // true
 *
 * // User with view only - hide menu
 * canUserSeeGraphActionMenu('access', { allowed_actions: ['view'] }) // false
 */
export function canUserSeeGraphActionMenu(
  graphPermissionLevel: 'admin' | 'access' | null | undefined,
  graph?: GraphInfo
): boolean {
  if (!graph || !graph.allowed_actions) {
    throw new Error(
      'canUserSeeGraphActionMenu: graph or allowed_actions is missing. ' +
      'This indicates the backend API is not returning permission data correctly. ' +
      'Check that all graph API endpoints include allowed_actions in their responses.'
    );
  }

  // Can see menu if user has any actions beyond just 'view'
  const actionsCount = graph.allowed_actions.length;
  const hasViewOnly = actionsCount === 1 && graph.allowed_actions.includes('view');
  return !hasViewOnly;
}

/**
 * **UI-ONLY CHECK:** Determines if a user can manage access for a graph (add/remove other users).
 *
 * **IMPORTANT:** This function is NOT security enforcement. It only controls UI element
 * visibility ("Manage Access" button). Actual security is enforced by backend endpoints.
 * See: `apps/langconnect/langconnect/api/graph_actions/permissions.py`
 *
 * **Phase 4 Complete:** This function now relies entirely on backend-provided `allowed_actions`.
 * The backend PermissionService handles all permission logic:
 * - Only admins can manage access (grant/revoke permissions for other users)
 * - Regular users with 'access' level cannot manage access
 *
 * @param graphPermissionLevel The user's permission level (deprecated parameter, not used anymore)
 * @param graph The graph object with allowed_actions (REQUIRED)
 * @returns True if the user can manage access for this graph
 * @throws Error if graph or allowed_actions is missing (indicates API integration issue)
 * @example
 * // Admin user - can manage access
 * canUserManageGraphAccess('admin', { allowed_actions: ['view', 'create_assistant', 'manage_access'] }) // true
 *
 * // Regular user - cannot manage access
 * canUserManageGraphAccess('access', { allowed_actions: ['view', 'create_assistant', 'revoke_own'] }) // false
 */
export function canUserManageGraphAccess(
  graphPermissionLevel: 'admin' | 'access' | null | undefined,
  graph?: GraphInfo
): boolean {
  if (!graph || !graph.allowed_actions) {
    throw new Error(
      'canUserManageGraphAccess: graph or allowed_actions is missing. ' +
      'This indicates the backend API is not returning permission data correctly. ' +
      'Check that all graph API endpoints include allowed_actions in their responses.'
    );
  }

  return graph.allowed_actions.includes('manage_access');
}
