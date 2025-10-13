import { Agent } from "@/types/agent";
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
 * Determines if a user can delete an assistant based on permissions.
 * 
 * Deletion rules:
 * - Default assistants (system-managed) cannot be deleted by anyone
 * - Only owners can delete custom assistants
 * - Editors and viewers cannot delete assistants
 * 
 * @param agent The agent to check
 * @returns True if the user can delete this assistant
 * @example
 * // Owner of custom assistant - can delete
 * canUserDeleteAssistant({ permission_level: 'owner', metadata: {} }) // true
 * 
 * // Editor of custom assistant - cannot delete
 * canUserDeleteAssistant({ permission_level: 'editor', metadata: {} }) // false
 * 
 * // Owner of default assistant - cannot delete (system-managed)
 * canUserDeleteAssistant({ permission_level: 'owner', metadata: { _x_oap_is_default: true } }) // false (user default assistant)
 */
export function canUserDeleteAssistant(agent: Agent): boolean {
  const isDefaultAgent = isUserDefaultAssistant(agent);
  const isOwner = agent.permission_level === 'owner';
  
  // Default assistants cannot be deleted
  if (isDefaultAgent) {
    return false;
  }
  
  // Only owners can delete custom assistants
  return isOwner;
}

/**
 * Determines if a user can edit an assistant based on permissions.
 * 
 * Edit rules:
 * - Default assistants cannot be edited
 * - Owners and editors can edit custom assistants
 * - Viewers cannot edit assistants
 * 
 * @param agent The agent to check
 * @returns True if the user can edit this assistant
 * @example
 * // Owner of custom assistant - can edit
 * canUserEditAssistant({ permission_level: 'owner', metadata: {} }) // true
 * 
 * // Editor of custom assistant - can edit
 * canUserEditAssistant({ permission_level: 'editor', metadata: {} }) // true
 * 
 * // Viewer of custom assistant - cannot edit
 * canUserEditAssistant({ permission_level: 'viewer', metadata: {} }) // false
 * 
 * // Owner of default assistant - cannot edit (system-managed)
 * canUserEditAssistant({ permission_level: 'owner', metadata: { _x_oap_is_default: true } }) // false (user default assistant)
 */
export function canUserEditAssistant(agent: Agent): boolean {
  const isDefaultAgent = isUserDefaultAssistant(agent);
  const permissionLevel = agent.permission_level;
  
  // Default assistants cannot be edited
  if (isDefaultAgent) {
    return false;
  }
  
  // Owners and editors can edit custom assistants
  return permissionLevel === 'owner' || permissionLevel === 'editor';
}

/**
 * Determines if a user can revoke their own access to an assistant.
 * 
 * Self-revocation rules:
 * - Editors and viewers can revoke their own access
 * - Owners cannot revoke their own access (they should delete the assistant instead)
 * - Default assistants cannot be revoked from (system-managed)
 * 
 * @param agent The agent to check
 * @returns True if the user can revoke their own access to this assistant
 * @example
 * // Editor of custom assistant - can revoke own access
 * canUserRevokeOwnAccess({ permission_level: 'editor', metadata: {} }) // true
 * 
 * // Viewer of custom assistant - can revoke own access
 * canUserRevokeOwnAccess({ permission_level: 'viewer', metadata: {} }) // true
 * 
 * // Owner of custom assistant - cannot revoke (should delete instead)
 * canUserRevokeOwnAccess({ permission_level: 'owner', metadata: {} }) // false
 * 
 * // Editor of default assistant - cannot revoke (system-managed)
 * canUserRevokeOwnAccess({ permission_level: 'editor', metadata: { _x_oap_is_default: true } }) // false (user default assistant)
 */
export function canUserRevokeOwnAccess(agent: Agent): boolean {
  const isDefaultAgent = isUserDefaultAssistant(agent);
  const permissionLevel = agent.permission_level;
  
  // Default assistants cannot be revoked from (system-managed)
  if (isDefaultAgent) {
    return false;
  }
  
  // Only editors and viewers can revoke their own access
  // Owners should use delete instead of revoke
  return permissionLevel === 'editor' || permissionLevel === 'viewer';
}

/**
 * Determines if a user can revoke their own access to a graph.
 * 
 * Self-revocation rules:
 * - Users with 'access' or 'admin' permissions can revoke their own access
 * - dev_admin users cannot revoke their own access (system protection)
 * - Users with no permission cannot revoke (nothing to revoke)
 * 
 * @param userRole The user's global role (dev_admin, business_admin, user, etc.)
 * @param graphPermissionLevel The user's permission level for this specific graph
 * @returns True if the user can revoke their own access to this graph
 * @example
 * // Regular user with access - can revoke
 * canUserRevokeOwnGraphAccess('user', 'access') // true
 * 
 * // Regular user with admin - can revoke  
 * canUserRevokeOwnGraphAccess('user', 'admin') // true
 * 
 * // Dev admin with access - cannot revoke (system protection)
 * canUserRevokeOwnGraphAccess('dev_admin', 'access') // false
 * 
 * // User with no access - cannot revoke (nothing to revoke)
 * canUserRevokeOwnGraphAccess('user', null) // false
 */
export function canUserRevokeOwnGraphAccess(
  userRole: string | null | undefined,
  graphPermissionLevel: 'admin' | 'access' | null | undefined
): boolean {
  // Must have some graph permission to revoke
  if (!graphPermissionLevel || (graphPermissionLevel !== 'admin' && graphPermissionLevel !== 'access')) {
    return false;
  }
  
  // dev_admin users cannot revoke their own access (system protection)
  if (userRole === 'dev_admin') {
    return false;
  }
  
  // All other users with graph access can revoke their own access
  return true;
}

/**
 * Determines if a user should see the graph action menu.
 * 
 * Action menu visibility rules:
 * - Users with 'admin' permission can see it (to manage access and potentially revoke own)
 * - Users with 'access' permission can see it (to revoke own access)
 * - Users with no permission cannot see it
 * 
 * @param graphPermissionLevel The user's permission level for this specific graph
 * @returns True if the user should see the graph action menu
 * @example
 * // Admin user - can see menu
 * canUserSeeGraphActionMenu('admin') // true
 * 
 * // Access user - can see menu  
 * canUserSeeGraphActionMenu('access') // true
 * 
 * // No permission - cannot see menu
 * canUserSeeGraphActionMenu(null) // false
 */
export function canUserSeeGraphActionMenu(
  graphPermissionLevel: 'admin' | 'access' | null | undefined
): boolean {
  return graphPermissionLevel === 'admin' || graphPermissionLevel === 'access';
}

/**
 * Determines if a user can manage access for a graph (add/remove other users).
 * 
 * Access management rules:
 * - Only users with 'admin' permission can manage access
 * - Users with 'access' permission cannot manage access
 * 
 * @param graphPermissionLevel The user's permission level for this specific graph
 * @returns True if the user can manage access for this graph
 * @example
 * // Admin user - can manage access
 * canUserManageGraphAccess('admin') // true
 * 
 * // Access user - cannot manage access
 * canUserManageGraphAccess('access') // false
 */
export function canUserManageGraphAccess(
  graphPermissionLevel: 'admin' | 'access' | null | undefined
): boolean {
  return graphPermissionLevel === 'admin';
}
