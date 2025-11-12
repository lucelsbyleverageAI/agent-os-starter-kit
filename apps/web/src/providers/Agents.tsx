"use client";

/**
 * ============================================================================
 * AGENTS PROVIDER - MULTI-LAYER CACHING ARCHITECTURE
 * ============================================================================
 *
 * This provider implements a sophisticated multi-layer caching system to solve
 * several critical challenges in a multi-user, multi-tab collaborative environment.
 *
 * ============================================================================
 * WHY IS THIS COMPLEX?
 * ============================================================================
 *
 * 1. MULTI-TAB SYNCHRONIZATION
 *    - Tab A creates an agent → Tab B needs to see it immediately
 *    - Tab C deletes an agent → Tabs A and B must remove it from their lists
 *    - Without version tracking, tabs would show stale data
 *
 * 2. MULTI-USER COLLABORATION
 *    - User A shares an agent with User B → B's UI updates in real-time
 *    - Permission changes need immediate UI reflection
 *    - System must handle concurrent access gracefully
 *
 * 3. NO WEBSOCKET/SSE INFRASTRUCTURE
 *    - We don't have WebSocket or Server-Sent Events
 *    - Polling is the ONLY way to notify tabs about backend changes
 *    - Alternative: Use React Query with polling (future enhancement)
 *
 * 4. PERFORMANCE OPTIMIZATION
 *    - Avoid unnecessary LangGraph API calls (expensive)
 *    - Minimize network requests with ETags
 *    - Cache aggressively, invalidate intelligently
 *
 * ============================================================================
 * CACHE LAYERS
 * ============================================================================
 *
 * LAYER 1: Graph Discovery Cache (2 hour TTL)
 *   - What: Available graph templates (agent blueprints)
 *   - Why long TTL: Templates rarely change (only when new agent types added)
 *   - Storage: localStorage with key `agents_graph_discovery_{userId}`
 *   - Invalidation: Backend increments `graphs_version` when templates change
 *
 * LAYER 2: Assistant List Cache (30 minute TTL)
 *   - What: User's accessible assistants (agent instances)
 *   - Why shorter TTL: Moderate churn (users create/delete agents regularly)
 *   - Storage: localStorage with key `agents_assistant_list_{userId}`
 *   - Invalidation: Backend increments `assistants_version` on mutations
 *
 * LAYER 3: HTTP ETags
 *   - What: Server-side cache validation via ETags
 *   - How: Backend generates ETag from version numbers
 *   - Result: HTTP 304 responses when data unchanged (no payload transfer)
 *   - See: apps/langconnect/langconnect/api/mirror_apis.py:64-73
 *
 * ============================================================================
 * VERSION TRACKING SYSTEM
 * ============================================================================
 *
 * BACKEND (LangConnect):
 *   - Maintains version counters in `cache_state` table:
 *     • graphs_version
 *     • assistants_version
 *     • schemas_version
 *     • threads_version
 *   - Increments version after ANY mutation:
 *     • Assistant created → assistants_version++
 *     • Permission granted → assistants_version++
 *     • Graph metadata updated → graphs_version++
 *   - See: apps/langconnect/langconnect/services/langgraph_sync.py:345,530,836
 *
 * FRONTEND (This File):
 *   - Polls `/api/langconnect/agents/mirror/cache-state` every 30 seconds
 *   - Computes version key: `g${graphs_version}-a${assistants_version}-s${schemas_version}`
 *   - Compares with cached version key in localStorage
 *   - Version mismatch → invalidate localStorage → refetch fresh data
 *
 * EXAMPLE FLOW:
 *   1. Tab A creates agent → Backend increments assistants_version (1 → 2)
 *   2. Tab B polls cache-state after 30s → sees version mismatch
 *   3. Tab B invalidates localStorage → refetches data → sees new agent
 *
 * ============================================================================
 * ALTERNATIVES CONSIDERED
 * ============================================================================
 *
 * ✅ React Query / SWR
 *    - Would simplify cache management significantly
 *    - Provides built-in devtools and stale-while-revalidate
 *    - STILL need version polling for multi-tab synchronization
 *    - Estimated migration effort: 2-3 days
 *
 * ✅ WebSockets / Server-Sent Events (SSE)
 *    - Would eliminate polling entirely
 *    - Push notifications for real-time updates
 *    - Requires backend infrastructure changes
 *    - Estimated implementation: 1-2 weeks
 *
 * ❌ Polling Individual Endpoints
 *    - Too many requests (graphs, assistants, schemas separately)
 *    - Version tracking is more efficient
 *
 * ❌ No Caching
 *    - Every page load = multiple LangGraph API calls
 *    - Unacceptable performance for users
 *
 * ============================================================================
 * IMPORTANT NOTES
 * ============================================================================
 *
 * - localStorage limits: ~5-10MB per domain (browser dependent)
 * - For power users with 100+ agents, monitor storage usage
 * - Cache invalidation is CRITICAL - never skip version checks
 * - Optimistic updates are used for instant UI feedback, then validated
 * - Background validation prevents stale state from persisting
 *
 * ============================================================================
 */

import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
// import { flushSync } from "react-dom"; // Removed unused import
import { getDeployments } from "@/lib/environment/deployments";
import {
  Agent,
  AgentDisplayItem,
  DiscoveryResponse,
  GraphInfo,
  AssistantInfo
} from "@/types/agent";

import { useAuthContext } from "./Auth";
import { useUserRole } from "./UserRole";
import { notify } from "@/utils/toast";
import { agentMessages } from "@/utils/toast-messages";
import { toast } from "sonner";
import { useQueryState } from "nuqs";
import { useDefaultAssistant } from "@/hooks/use-default-assistant";


/**
 * Merge graphs and assistants into a unified display format for admin UI.
 *
 * This function creates AgentDisplayItem[] which enables the admin dashboard
 * to show both graph templates and assistant instances in a single list.
 *
 * **Purpose:**
 * - Dev admins need to see graph templates alongside assistants
 * - Permission management UI needs grouped view (assistants by graph)
 * - Enables "Initialize Platform" workflow for new graphs
 *
 * **Behavior:**
 * - For dev_admin: Includes graphs AND assistants
 * - For other users: Only includes assistants (no graphs)
 *
 * **Output:**
 * - Array of AgentDisplayItem with type="graph" or type="assistant"
 * - Consumed by admin-dashboard.tsx and add-permission-modal.tsx
 *
 * @param graphs - Graph templates with permission metadata
 * @param assistants - Assistant instances with permission metadata
 * @param userRole - User's role ('dev_admin' | 'business_admin' | 'user')
 * @returns Unified array for admin UI display
 */
function mergeGraphsAndAssistants(
  graphs: GraphInfo[],
  assistants: AssistantInfo[],
  userRole: string
): AgentDisplayItem[] {
  const displayItems: AgentDisplayItem[] = [];
  
  // Add graphs (for dev admins to see initialization opportunities)
  if (userRole === 'dev_admin') {
    graphs.forEach(graph => {
      displayItems.push({
        id: `graph_${graph.graph_id}`,
        type: "graph",
        name: graph.name || graph.graph_id.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
        description: graph.description || `Graph with ${graph.assistants_count} assistant${graph.assistants_count !== 1 ? 's' : ''}`,
        graph_id: graph.graph_id,
        needs_initialization: graph.needs_initialization,
        schema_accessible: graph.schema_accessible,
        assistants_count: graph.assistants_count,
        permission_level: graph.user_permission_level as "owner" | "editor" | "viewer" | "admin",
        created_at: graph.created_at,
      });
    });
  }
  
  // Add assistants with permission metadata
  assistants.forEach(assistant => {
    displayItems.push({
      id: `assistant_${assistant.assistant_id}`,
      type: "assistant",
      name: assistant.name,
      description: assistant.description ? assistant.description : undefined,
      graph_id: assistant.graph_id,
      permission_level: assistant.permission_level,
      owner_id: assistant.owner_id,
      owner_display_name: assistant.owner_display_name,
      assistant_id: assistant.assistant_id,
      created_at: assistant.created_at,
      updated_at: assistant.updated_at,
      metadata: assistant.metadata,
      // TODO: Extract supported configs from metadata/config
      supportedConfigs: undefined,
    });
  });
  
  return displayItems;
}

/**
 * Convert AssistantInfo from discovery response to Agent format.
 *
 * This conversion is necessary because:
 * - Backend returns AssistantInfo (minimal API format from LangConnect)
 * - Frontend needs Agent (rich format with LangGraph SDK compatibility)
 * - Conversion adds deploymentId and normalizes field structure
 *
 * @param item - Assistant information from backend API
 * @param deploymentId - Deployment ID to attach to the agent
 * @returns Fully formed Agent object for frontend consumption
 */
function convertAssistantInfoToAgent(item: AssistantInfo, deploymentId: string): Agent {
  return {
    assistant_id: item.assistant_id,
    graph_id: item.graph_id,
    name: item.name,
    description: item.description || undefined,
    config: {},
    metadata: item.metadata || {},
    created_at: item.created_at,
    updated_at: item.updated_at || item.created_at,
    version: 1,
    deploymentId,
    supportedConfigs: undefined, // Will be filled during enrichment
    permission_level: item.permission_level,
    allowed_actions: item.allowed_actions, // Phase 4: Pass through backend permissions
    owner_id: item.owner_id,
    owner_display_name: item.owner_display_name,
    type: "assistant",
    needs_initialization: false,
    schema_accessible: true,
    tags: item.tags || [],
  };
}

/**
 * ✅ NEW: Convert LightweightAssistantInfo from cache to LightweightAgent format.
 *
 * This keeps agents in lightweight format throughout the state, reducing memory usage
 * by 97% compared to full Agent objects. Full details (config/metadata) are only
 * fetched on-demand via hydrateAgent() when starting a chat or editing.
 *
 * @param item - Lightweight assistant info from cache
 * @param deploymentId - Deployment ID to attach to the agent
 * @returns Lightweight agent object for state management
 */
function convertLightweightToAgent(item: LightweightAssistantInfo, deploymentId: string): LightweightAgent {
  return {
    assistant_id: item.assistant_id,
    graph_id: item.graph_id,
    name: item.name,
    description: item.description,
    deploymentId,
    permission_level: item.permission_level,
    allowed_actions: item.allowed_actions || [],
    owner_id: item.owner_id,
    owner_display_name: item.owner_display_name,
    tags: item.tags || [],
    created_at: item.created_at,
    updated_at: item.updated_at,
    version: 1,
    type: "assistant",
    needs_initialization: false,
    schema_accessible: true,
    metadata: item.metadata,
    _isLightweight: true,
  };
}

// ============================================================================
// LAYERED CACHING CONFIGURATION
// ============================================================================
//
// These TTLs balance freshness vs performance:
// - Longer TTL = Fewer network requests, but risk showing stale data
// - Shorter TTL = More network requests, but fresher data
//
// The version tracking system (polling every 30s) provides a safety net,
// invalidating caches immediately when backend versions change, regardless of TTL.
//
// Layer 1: Graph Discovery Cache (LONG-LIVED - graphs rarely change)
// - Templates only change when devs add new agent types
// - Safe to cache for hours since version polling will invalidate if needed
const GRAPH_DISCOVERY_CACHE_DURATION = 2 * 60 * 60 * 1000; // 2 hours
const GRAPH_DISCOVERY_CACHE_KEY_PREFIX = 'agents_graph_discovery_';

// Layer 2: Assistant List Cache - DISABLED
// Assistant list caching was disabled to avoid localStorage quota issues.
// Backend ETag caching (3-min TTL) provides sufficient performance.

// Note: Per-assistant caches were removed for simplification.
// Full assistant details are fetched on-demand (not cached in localStorage).

// ✅ LAYERED CACHE INTERFACES
interface GraphDiscoveryCache {
  valid_graphs: GraphInfo[];
  invalid_graphs: GraphInfo[];
  scan_metadata: any;
  timestamp: number;
  userId: string;
  version: string;
}

/**
 * @deprecated Assistant list caching disabled to avoid localStorage quota issues.
 * Kept for backward compatibility with getAssistantListCache signature.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface AssistantListCache {
  assistants: AssistantInfo[];
  assistant_counts: any;
  user_role: string;
  is_dev_admin: boolean;
  deployment_id: string;
  deployment_name: string;
  timestamp: number;
  userId: string;
  version: string;
}

/**
 * ✅ NEW: Lightweight assistant metadata for localStorage caching
 *
 * Only stores essential fields to avoid quota issues:
 * - Full assistant objects: ~10-20KB each (with config/metadata)
 * - Lightweight objects: ~650 bytes each (96% size reduction!)
 *
 * For 100 assistants:
 * - Old approach: ~2MB (hit Safari's 5MB limit)
 * - New approach: ~65KB (well below quota)
 *
 * Includes UI-essential fields (description, permissions, actions) but excludes
 * heavy fields (config, metadata, context) that are only needed during chat.
 */
interface LightweightAssistantInfo {
  assistant_id: string;
  graph_id: string;
  name: string;
  description?: string; // Include for UI cards
  permission_level: "owner" | "editor" | "viewer" | "admin";
  allowed_actions: string[]; // Include for UI permissions (edit, delete, share buttons)
  created_at: string;
  updated_at: string;
  owner_id: string;
  owner_display_name?: string; // Include for UI display
  tags?: string[];
  metadata?: Record<string, any>; // Include for checking default assistant flag
  // Flag to indicate this is cached lightweight data
  _isLightweight: true;
}

/**
 * ✅ NEW: Lightweight assistant list cache with quota-safe storage
 */
interface LightweightAssistantListCache {
  assistants: LightweightAssistantInfo[];
  assistant_counts: {
    total: number;
    owned: number;
    shared: number;
  };
  user_role: 'dev_admin' | 'business_admin' | 'user';
  is_dev_admin: boolean;
  deployment_id: string;
  deployment_name: string;
  timestamp: number;
  userId: string;
  version: string;
}

/**
 * ✅ NEW: Lightweight Agent for React state management
 *
 * Similar to LightweightAssistantInfo but includes deploymentId and UI fields.
 * Used in React state to reduce memory usage by 97% (vs full Agent objects).
 *
 * When full agent details (config, metadata) are needed:
 * - Use hydrateAgent() to fetch and convert to full Agent
 * - Full agents are used when starting chats or editing configurations
 */
interface LightweightAgent {
  assistant_id: string;
  graph_id: string;
  name: string;
  description?: string;
  deploymentId: string;
  permission_level: "owner" | "editor" | "viewer" | "admin";
  allowed_actions?: string[];
  owner_id?: string;
  owner_display_name?: string;
  tags?: string[];
  created_at: string;
  updated_at: string;
  version: number;
  type: "assistant";
  needs_initialization: boolean;
  schema_accessible: boolean;
  metadata?: Record<string, any>;
  _isLightweight: true;
}

/**
 * Type guard to check if an agent is lightweight
 */
function isLightweightAgent(agent: Agent | LightweightAgent): agent is LightweightAgent {
  return '_isLightweight' in agent && agent._isLightweight === true;
}

/**
 * Type guard to check if an agent is full (has config/metadata)
 */
function isFullAgent(agent: Agent | LightweightAgent): agent is Agent {
  return !('_isLightweight' in agent) || agent._isLightweight !== true;
}

// Cache configuration for lightweight assistant caching
const ASSISTANT_LIST_CACHE_DURATION = 30 * 60 * 1000; // 30 minutes
const ASSISTANT_LIST_CACHE_KEY_PREFIX = 'agents_assistant_list_';

/**
 * ✅ STORAGE MONITORING UTILITY
 *
 * Monitors localStorage usage and warns if approaching browser limits.
 * Different browsers have different limits:
 * - Chrome/Edge: ~10MB
 * - Firefox: ~10MB
 * - Safari: ~5MB (strictest)
 *
 * We target <1MB for safety across all browsers.
 */
function monitorLocalStorageUsage(context: string = 'AgentsProvider') {
  try {
    let totalSize = 0;
    const items: Array<{ key: string; sizeKB: number }> = [];

    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key) {
        const value = localStorage.getItem(key);
        if (value) {
          const sizeKB = Math.round(value.length / 1024);
          totalSize += sizeKB;
          items.push({ key, sizeKB });
        }
      }
    }

    const totalMB = (totalSize / 1024).toFixed(2);

    // Log summary
    console.log(`[${context}] 📊 localStorage usage: ${totalMB}MB (${totalSize}KB)`);

    // Warn if approaching limits
    if (totalSize > 4096) { // > 4MB
      console.warn(`[${context}] ⚠️ localStorage usage high (${totalMB}MB)! Approaching Safari's 5MB limit.`);
    } else if (totalSize > 2048) { // > 2MB
      console.warn(`[${context}] ⚠️ localStorage usage moderate (${totalMB}MB). Consider cleanup if issues arise.`);
    }

    // Log top 5 largest items
    const topItems = items.sort((a, b) => b.sizeKB - a.sizeKB).slice(0, 5);
    console.log(`[${context}] Top storage consumers:`, topItems.map(item => `${item.key}: ${item.sizeKB}KB`).join(', '));

    return { totalKB: totalSize, totalMB: parseFloat(totalMB), items };
  } catch (error) {
    console.error(`[${context}] Error monitoring localStorage:`, error);
    return { totalKB: 0, totalMB: 0, items: [] };
  }
}

// EnhancementStatusCache removed

// Per-assistant cache interfaces removed

type AgentsContextType = {
  /**
   * Array of agents with permission metadata (may be lightweight or full)
   * - Lightweight agents: Used for list views, only have essential fields
   * - Full agents: Have config/metadata, used when starting chats or editing
   */
  agents: (Agent | LightweightAgent)[];
  /**
   * Structured display items for UI
   */
  displayItems: AgentDisplayItem[];
  /**
   * Refreshes the agents list by fetching the latest agents from the API,
   * and updating the state.
   */
  refreshAgents: (silent?: boolean) => Promise<void>;
  /**
   * Whether the agents list is currently loading.
   */
  loading: boolean;
  /**
   * Whether the agents list is currently refreshing.
   */
  refreshAgentsLoading: boolean;
  /**
   * Discovery metadata
   */
  discoveryData: DiscoveryResponse | null;
  /**
   * Error state
   */
  error: string | null;
  /**
   * Get the user's permission level for a specific graph
   */
  getGraphPermissionLevel: (graphId: string) => "admin" | "access" | null;
  /**
   * Invalidate discovery cache (call after assistant mutations)
   */
  invalidateDiscoveryCache: (userId?: string, deploymentId?: string) => void;
  /**
   * Invalidate assistant caches (call after assistant mutations)
   */
  invalidateAssistantCaches: (assistantId: string) => void;
  /**
   * Invalidate all assistant caches
   */
  invalidateAllAssistantCaches: () => void;
  /**
   * ✅ NEW: Layered cache invalidation methods
   */
  /**
   * Invalidate graph discovery cache (Layer 1 - rare operation)
   */
  invalidateGraphDiscoveryCache: (userId?: string) => void;
  /**
   * Invalidate assistant list cache (Layer 2 - for assistant operations)
   */
  invalidateAssistantListCache: (userId?: string) => void;
  /**
   * Invalidate enhancement status cache (Layer 3 - for permission operations)
   */
  invalidateEnhancementStatusCache: (userId?: string) => void;
  /**
   * Debug function to inspect cache state
   */
  debugCacheState: () => void;
  /**
   * Manually add an agent to the list (for immediate UI updates after creation)
   */
  addAgentToList: (agent: Agent | LightweightAgent) => void;
  /**
   * ✅ NEW: Hydrate a lightweight agent to full agent (fetch config/metadata)
   * Used when transitioning from list view to chat or config editing
   */
  hydrateAgent: (assistantId: string) => Promise<Agent>;
  /**
   * Default assistant state and methods (shared across all components)
   */
  defaultAssistant: { assistant_id: string; assistant_name?: string; user_id: string; graph_id?: string; created_at: string; updated_at: string } | null;
  defaultAssistantLoading: boolean;
  setDefaultAssistant: (assistantId: string) => Promise<any>;
  clearDefaultAssistant: () => Promise<any>;
  refreshDefaultAssistant: () => Promise<void>;
};

const AgentsContext = createContext<AgentsContextType | undefined>(undefined);

// Global debug function for browser console
if (typeof window !== 'undefined') {
  (window as any).debugAgentCache = () => {
    const keys = Object.keys(localStorage).filter(key => 
      key.includes('agents_') || key.includes('assistant_') || key.includes('enriched_')
    );
    keys.forEach(key => console.log(`  - ${key}`));

  };
  
  (window as any).clearAgentCache = () => {
    const keys = Object.keys(localStorage).filter(key => 
      key.includes('agents_') || key.includes('assistant_') || key.includes('enriched_')
    );
    keys.forEach(key => localStorage.removeItem(key));
  };
}

export const AgentsProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const { session } = useAuthContext();
  const { userRole, isDevAdmin: _isDevAdmin, loading: roleLoading, roleValidated } = useUserRole();
  const deployments = getDeployments();
  const [selectedDeploymentId] = useQueryState("deploymentId");
  const { defaultAssistant, setDefaultAssistant, clearDefaultAssistant, refreshDefaultAssistant, isLoading: defaultLoading } = useDefaultAssistant();

  const [agents, setAgents] = useState<(Agent | LightweightAgent)[]>([]);
  const [displayItems, setDisplayItems] = useState<AgentDisplayItem[]>([]);
  const [discoveryData, setDiscoveryData] = useState<DiscoveryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const _firstRequestMade = useRef(false);
  const [loading, setLoading] = useState(true); // Start as true to show loading state on initial render
  const [refreshAgentsLoading, setRefreshAgentsLoading] = useState(false);

  // Legacy cache configuration (unused but kept for reference)
  const _AGENTS_CACHE_KEY = 'oap_agents_cache';
  const _AGENTS_CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

  // ============================================================================
  // VERSION-AWARE CACHE STATE
  // ============================================================================
  //
  // These version numbers come from the backend's `cache_state` table.
  // The backend increments versions after ANY mutation (create, update, delete).
  //
  // How it works:
  // 1. Frontend polls /cache-state every 30 seconds
  // 2. Compares received versions with locally cached versions
  // 3. If mismatch → invalidates localStorage → fetches fresh data
  //
  // This ensures multi-tab synchronization:
  // - Tab A creates agent → backend increments assistants_version
  // - Tab B polls → sees new version → invalidates cache → sees new agent
  //
  // See backend implementation:
  // - apps/langconnect/langconnect/services/langgraph_sync.py:923-958
  // - apps/langconnect/langconnect/api/mirror_apis.py:28-38
  //
  const [graphsVersion, setGraphsVersion] = useState<number | null>(null);
  const [assistantsVersion, setAssistantsVersion] = useState<number | null>(null);
  const [schemasVersion, setSchemasVersion] = useState<number | null>(null);

  /**
   * Compute a combined version key for cache validation.
   *
   * Format: "g{graphs_version}-a{assistants_version}-s{schemas_version}"
   * Example: "g1-a24-s5"
   *
   * This key is stored in localStorage alongside cached data.
   * When version key changes, we know backend data changed → invalidate cache.
   */
  const computeVersionKey = useCallback(() => {
    const g = graphsVersion ?? 0;
    const a = assistantsVersion ?? 0;
    const s = schemasVersion ?? 0;
    return `g${g}-a${a}-s${s}`;
  }, [graphsVersion, assistantsVersion, schemasVersion]);

  /**
   * Fetch current cache state from backend.
   *
   * This polls the /cache-state endpoint which returns version numbers
   * for all cache types. The backend updates these versions after mutations.
   *
   * Polling frequency: Every 30 seconds
   * Why 30s? Balance between responsiveness and server load:
   * - Shorter (e.g., 10s) = Too many requests for marginal benefit
   * - Longer (e.g., 60s) = Users wait longer to see changes from other tabs
   *
   * With WebSockets/SSE, this polling would be eliminated entirely.
   */
  const fetchCacheState = useCallback(async () => {
    if (!session?.accessToken) return;
    try {
      const res = await fetch(`/api/langconnect/agents/mirror/cache-state`, {
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
          'Content-Type': 'application/json',
        },
      });
      if (!res.ok) return;
      const data = await res.json();
      setGraphsVersion(data.graphs_version ?? null);
      setAssistantsVersion(data.assistants_version ?? null);
      setSchemasVersion(data.schemas_version ?? null);
    } catch (_e) {
      // Silently fail - cache will fall back to TTL-based invalidation
      // This prevents errors during network issues or API downtime
    }
  }, [session?.accessToken]);

  /**
   * Poll cache state every 30 seconds for version-aware invalidation.
   *
   * This is the heartbeat of multi-tab synchronization. Without this polling,
   * tabs would only see changes on page refresh or cache TTL expiry.
   *
   * The interval is cleaned up when component unmounts or user logs out.
   */
  useEffect(() => {
    if (!session?.accessToken) return;

    // Fetch immediately on mount
    fetchCacheState();

    // Then poll every 30 seconds
    const interval = setInterval(fetchCacheState, 30000);

    return () => clearInterval(interval);
  }, [session?.accessToken]); // Only depend on accessToken, not fetchCacheState

  // Auto-set first assistant as default if user has no default
  useEffect(() => {
    // Skip if still loading agents or default assistant
    if (loading || defaultLoading) return;

    // Skip if no agents loaded yet
    if (agents.length === 0) return;

    // Skip if user already has a default set
    if (defaultAssistant) return;

    // Get the first assistant (sorted by created_at, most recent first)
    const sortedAgents = [...agents].sort((a, b) => {
      const dateA = new Date(a.created_at).getTime();
      const dateB = new Date(b.created_at).getTime();
      return dateB - dateA; // Most recent first
    });

    const firstAssistant = sortedAgents[0];
    if (firstAssistant) {
      setDefaultAssistant(firstAssistant.assistant_id);
    }
  }, [agents, defaultAssistant, loading, defaultLoading, setDefaultAssistant]);

  // ============================================================================
  // LOCALSTORAGE UTILITIES WITH MONITORING
  // ============================================================================
  //
  // localStorage has browser-dependent limits (typically 5-10MB per domain).
  // For power users with 100+ agents, we could approach these limits.
  // This monitoring helps detect potential issues before they cause errors.
  //
  /**
   * Check localStorage usage and warn if approaching browser limits.
   *
   * Typical limits:
   * - Chrome/Edge: ~10MB
   * - Firefox: ~10MB
   * - Safari: ~5MB
   *
   * We warn at 4MB (80% of minimum limit) to catch issues early.
   */
  const checkStorageUsage = useCallback(() => {
    try {
      let totalBytes = 0;
      for (const key in localStorage) {
        if (Object.prototype.hasOwnProperty.call(localStorage, key)) {
          totalBytes += (localStorage[key].length + key.length) * 2; // UTF-16 uses 2 bytes per char
        }
      }
      const usageMB = totalBytes / (1024 * 1024);

      // Warn if approaching limits (4MB = 80% of 5MB Safari limit)
      if (usageMB > 4) {
        console.warn(
          `[AgentsProvider] localStorage usage (${usageMB.toFixed(2)}MB) is approaching browser limits. ` +
          `Consider clearing old caches or reducing agent count.`
        );
      }

      return usageMB;
    } catch (error) {
      console.warn('[AgentsProvider] Failed to check storage usage:', error);
      return 0;
    }
  }, []);

  // ============================================================================
  // LAYERED CACHE UTILITIES (version-aware)
  // ============================================================================

  /**
   * Get graph discovery cache from localStorage.
   *
   * This cache stores available graph templates (agent blueprints).
   * TTL: 2 hours (templates rarely change)
   *
   * Returns null if:
   * - Cache doesn't exist
   * - Cache is expired (past TTL)
   * - Version mismatch (backend data changed)
   *
   * @param userId - User ID for cache isolation
   * @param expectedVersion - Expected version key (from backend)
   * @returns Cached data or null
   */
  const getGraphDiscoveryCache = useCallback((userId: string, expectedVersion: string): GraphDiscoveryCache | null => {
    try {
      const cached = localStorage.getItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`);
      if (!cached) return null;
      const data = JSON.parse(cached) as GraphDiscoveryCache;
      const now = Date.now();

      // Check TTL expiry
      if (now - data.timestamp > GRAPH_DISCOVERY_CACHE_DURATION) {
        localStorage.removeItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`);
        return null;
      }

      // Check version match (invalidate if backend changed)
      if (!data.version || data.version !== expectedVersion) {
        localStorage.removeItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`);
        return null;
      }

      return data;
    } catch (error) {
      console.warn('[AgentsProvider] Failed to read graph discovery cache:', error);
      return null;
    }
  }, []);

  /**
   * Store graph discovery cache in localStorage.
   *
   * Includes storage usage monitoring to detect potential quota issues.
   *
   * @param userId - User ID for cache isolation
   * @param graphData - Data to cache
   * @param versionKey - Current backend version key
   */
  const setGraphDiscoveryCache = useCallback((userId: string, graphData: { valid_graphs: GraphInfo[]; invalid_graphs: GraphInfo[]; scan_metadata: any }, versionKey: string) => {
    try {
      const cacheData: GraphDiscoveryCache = {
        valid_graphs: graphData.valid_graphs,
        invalid_graphs: graphData.invalid_graphs,
        scan_metadata: graphData.scan_metadata,
        timestamp: Date.now(),
        userId,
        version: versionKey,
      };
      localStorage.setItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`, JSON.stringify(cacheData));

      // Monitor storage usage after write
      checkStorageUsage();
    } catch (error) {
      console.warn('[AgentsProvider] Failed to write graph discovery cache:', error);
      // If quota exceeded, try clearing old caches
      if (error instanceof DOMException && error.name === 'QuotaExceededError') {
        console.warn('[AgentsProvider] Storage quota exceeded. Consider clearing old agent caches.');
      }
    }
  }, [checkStorageUsage]);

  const invalidateGraphDiscoveryCache = useCallback((userId: string) => {
    try {
      localStorage.removeItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`);
    } catch (error) {
      console.warn('Failed to invalidate graph discovery cache:', error);
    }
  }, []);

  /**
   * Get assistant list cache from localStorage.
   *
   * This cache stores the user's accessible assistants (agent instances).
   * TTL: 30 minutes (moderate churn - users create/edit/delete agents regularly)
   *
   * Returns null if:
   * - Cache doesn't exist
   * - Cache is expired (past TTL)
   * - Version mismatch (backend data changed)
   *
   * @param userId - User ID for cache isolation
   * @param expectedVersion - Expected version key (from backend)
   * @returns Cached data or null
   */
  /**
   * ✅ OPTIMIZED: Get lightweight assistant list from localStorage cache
   *
   * Returns cached lightweight assistant metadata if:
   * 1. Cache exists for this user
   * 2. Cache version matches backend version
   * 3. Cache hasn't expired (30 minute TTL)
   * 4. Cache size is reasonable (< 1MB, otherwise it's an old full-object cache)
   *
   * Lightweight cache stores only essential fields (~500 bytes per assistant)
   * vs full objects (~10-20KB each), avoiding localStorage quota issues.
   */
  const getAssistantListCache = useCallback((userId: string, expectedVersion: string): LightweightAssistantListCache | null => {
    try {
      const cacheKey = `${ASSISTANT_LIST_CACHE_KEY_PREFIX}${userId}`;
      const cached = localStorage.getItem(cacheKey);

      if (!cached) {
        return null;
      }

      // ✅ NEW: Check cache size to detect old full-object caches
      const cacheSizeKB = Math.round(cached.length / 1024);
      if (cacheSizeKB > 1024) { // > 1MB indicates old full-object cache
        console.warn(`[AgentsProvider] ⚠️ Detected oversized assistant cache (${cacheSizeKB}KB). Clearing old cache...`);
        localStorage.removeItem(cacheKey);
        return null;
      }

      const parsedCache: LightweightAssistantListCache = JSON.parse(cached);

      // Validate cache version
      if (parsedCache.version !== expectedVersion) {
        console.log('[AgentsProvider] Assistant cache version mismatch, invalidating...');
        localStorage.removeItem(cacheKey);
        return null;
      }

      // Validate cache expiration
      const now = Date.now();
      const age = now - parsedCache.timestamp;
      if (age > ASSISTANT_LIST_CACHE_DURATION) {
        console.log('[AgentsProvider] Assistant cache expired, invalidating...');
        localStorage.removeItem(cacheKey);
        return null;
      }

      console.log(`[AgentsProvider] ✅ Using cached assistant list (${parsedCache.assistants.length} assistants, ${cacheSizeKB}KB, age: ${Math.round(age / 1000)}s)`);
      return parsedCache;
    } catch (error) {
      console.error('[AgentsProvider] Error reading assistant list cache:', error);
      return null;
    }
  }, []);

  /**
   * ✅ OPTIMIZED: Store lightweight assistant list in localStorage cache
   *
   * Converts full AssistantInfo objects to lightweight metadata before caching.
   * This reduces storage by ~97% (50KB vs 2MB for 100 assistants).
   *
   * Includes automatic quota monitoring and cleanup on failure.
   */
  const setAssistantListCache = useCallback((userId: string, assistantData: { assistants: AssistantInfo[]; assistant_counts: any; user_role: 'dev_admin' | 'business_admin' | 'user'; is_dev_admin: boolean; deployment_id: string; deployment_name: string }, versionKey: string) => {
    try {
      // Convert to lightweight format
      const lightweightAssistants: LightweightAssistantInfo[] = assistantData.assistants.map(a => ({
        assistant_id: a.assistant_id,
        graph_id: a.graph_id,
        name: a.name,
        description: a.description ?? undefined, // Include for UI cards, convert null to undefined
        permission_level: a.permission_level,
        allowed_actions: a.allowed_actions || [], // Include for UI permissions
        created_at: a.created_at,
        updated_at: a.updated_at ?? a.created_at, // Fallback to created_at if updated_at is missing
        owner_id: a.owner_id,
        owner_display_name: a.owner_display_name, // Include for UI display
        tags: a.tags,
        metadata: a.metadata ? {
          _x_oap_is_default: a.metadata._x_oap_is_default,
          created_by: a.metadata.created_by,
          _x_oap_is_primary: a.metadata._x_oap_is_primary,
        } : undefined, // Only store essential flags to reduce cache size (99% reduction: 10KB → 50 bytes per assistant)
        _isLightweight: true as const
      }));

      const cacheData: LightweightAssistantListCache = {
        assistants: lightweightAssistants,
        assistant_counts: assistantData.assistant_counts,
        user_role: assistantData.user_role,
        is_dev_admin: assistantData.is_dev_admin,
        deployment_id: assistantData.deployment_id,
        deployment_name: assistantData.deployment_name,
        timestamp: Date.now(),
        userId,
        version: versionKey
      };

      const cacheKey = `${ASSISTANT_LIST_CACHE_KEY_PREFIX}${userId}`;
      const serialized = JSON.stringify(cacheData);

      // Monitor storage usage
      const sizeKB = Math.round(serialized.length / 1024);
      console.log(`[AgentsProvider] 💾 Caching ${lightweightAssistants.length} assistants (${sizeKB}KB)`);

      localStorage.setItem(cacheKey, serialized);

      // Monitor overall localStorage usage after caching
      monitorLocalStorageUsage('AgentsProvider');
    } catch (error) {
      // Handle quota exceeded error gracefully
      if (error instanceof DOMException && error.name === 'QuotaExceededError') {
        console.error('[AgentsProvider] ⚠️ localStorage quota exceeded, clearing old caches...');

        // Clear old graph discovery cache to free space
        try {
          localStorage.removeItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`);
          // Retry write after clearing
          const cacheKey = `${ASSISTANT_LIST_CACHE_KEY_PREFIX}${userId}`;
          const lightweightAssistants: LightweightAssistantInfo[] = assistantData.assistants.map(a => ({
            assistant_id: a.assistant_id,
            graph_id: a.graph_id,
            name: a.name,
            description: a.description ?? undefined, // Include for UI cards, convert null to undefined
            permission_level: a.permission_level,
            allowed_actions: a.allowed_actions || [], // Include for UI permissions
            created_at: a.created_at,
            updated_at: a.updated_at ?? a.created_at, // Fallback to created_at if updated_at is missing
            owner_id: a.owner_id,
            owner_display_name: a.owner_display_name, // Include for UI display
            tags: a.tags,
            metadata: a.metadata ? {
              _x_oap_is_default: a.metadata._x_oap_is_default,
              created_by: a.metadata.created_by,
              _x_oap_is_primary: a.metadata._x_oap_is_primary,
            } : undefined, // Only store essential flags to reduce cache size (99% reduction: 10KB → 50 bytes per assistant)
            _isLightweight: true as const
          }));
          const cacheData: LightweightAssistantListCache = {
            assistants: lightweightAssistants,
            assistant_counts: assistantData.assistant_counts,
            user_role: assistantData.user_role,
            is_dev_admin: assistantData.is_dev_admin,
            deployment_id: assistantData.deployment_id,
            deployment_name: assistantData.deployment_name,
            timestamp: Date.now(),
            userId,
            version: versionKey
          };
          localStorage.setItem(cacheKey, JSON.stringify(cacheData));
          console.log('[AgentsProvider] ✅ Successfully cached after cleanup');
        } catch (retryError) {
          console.error('[AgentsProvider] Failed to recover from quota exceeded error:', retryError);
        }
      } else {
        console.error('[AgentsProvider] Error setting assistant list cache:', error);
      }
    }
  }, []);

  /**
   * ✅ OPTIMIZED: Invalidate assistant list cache
   */
  const invalidateAssistantListCache = useCallback((userId: string) => {
    try {
      const cacheKey = `${ASSISTANT_LIST_CACHE_KEY_PREFIX}${userId}`;
      localStorage.removeItem(cacheKey);
      console.log('[AgentsProvider] Invalidated assistant list cache');
    } catch (error) {
      console.error('[AgentsProvider] Error invalidating assistant list cache:', error);
    }
  }, []);

  // Enhancement status cache removed
  const invalidateEnhancementStatusCache = useCallback((_userId?: string) => {}, []);

  // Smart invalidation utilities for layered caching
  const invalidateDiscoveryCache = useCallback((userId: string) => {
    // Legacy function - now invalidates all layers for compatibility
    invalidateGraphDiscoveryCache(userId);
    invalidateAssistantListCache(userId);
    invalidateEnhancementStatusCache(userId);
  }, [invalidateGraphDiscoveryCache, invalidateAssistantListCache, invalidateEnhancementStatusCache]);

  // Per-assistant caches removed

  // Cache invalidation utilities
  const invalidateAssistantCaches = useCallback((_assistantId: string) => {}, []);

  const invalidateAllAssistantCaches = useCallback(() => {}, []);

  /**
   * Helper function to fetch fresh discovery response
   */
  const fetchDiscoveryResponse = useCallback(async (deploymentId: string): Promise<{ response: DiscoveryResponse; duration: number }> => {
    const discoveryStart = Date.now();
    
    const apiResponse = await fetch(
      `/api/langconnect/user/accessible-graphs?deploymentId=${deploymentId}`,
      {
        headers: {
          Authorization: `Bearer ${session?.accessToken}`,
          'Content-Type': 'application/json',
        },
      }
    );

    if (!apiResponse.ok) {
      const errorText = await apiResponse.text();
      throw new Error(`Discovery failed: ${apiResponse.status} ${errorText}`);
    }

    const discoveryResponse: DiscoveryResponse = await apiResponse.json();
    const duration = Date.now() - discoveryStart;
    
    return { response: discoveryResponse, duration };
  }, [session?.accessToken]);

  /**
   * ✅ OPTIMIZED LAYERED DISCOVERY SYSTEM
   * Load agents using the new multi-layer caching system for maximum performance
   */
  const loadAgents = useCallback(async (useCache: boolean = true): Promise<void> => {
    if (!session?.accessToken) return;
    
    const userId = session.user?.id;
    if (!userId) return;
    
    // Ensure we have deployments
    if (!deployments || deployments.length === 0) {
      console.error('No deployments available');
      setError('No deployments configured');
      setLoading(false);
      return;
    }

    // Use selected deployment if provided, otherwise fallback to default/first
    const fallbackDeployment = deployments.find((d) => d.isDefault) || deployments[0];
    const deployment = (selectedDeploymentId && deployments.find(d => d.id === selectedDeploymentId)) || fallbackDeployment;

    // ✅ LAYERED CACHE CHECKING
    if (useCache) {
      // Fetch current backend cache versions
      await fetchCacheState();
      const versionKey = computeVersionKey();

      // Check both graph and assistant caches
      const graphData = getGraphDiscoveryCache(userId, versionKey);
      const assistantData = getAssistantListCache(userId, versionKey);

      // ✅ FULL CACHE HIT: Both graphs and assistants cached
      if (graphData && assistantData) {
        console.log('[AgentsProvider] 🚀 Full cache hit! Using cached lightweight data (graphs + assistants)');

        // ✅ NEW: Keep assistants in lightweight format (97% memory reduction!)
        // Convert cached lightweight data directly to LightweightAgent (no full AssistantInfo step)
        const lightweightAgents: LightweightAgent[] = assistantData.assistants.map(lightweight =>
          convertLightweightToAgent(lightweight, deployment.id)
        );

        // Create minimal AssistantInfo for display items (UI needs this structure)
        const assistantInfoForDisplay: AssistantInfo[] = assistantData.assistants.map(lightweight => ({
          assistant_id: lightweight.assistant_id,
          graph_id: lightweight.graph_id,
          name: lightweight.name,
          description: lightweight.description || '',
          permission_level: lightweight.permission_level,
          created_at: lightweight.created_at,
          updated_at: lightweight.updated_at,
          owner_id: lightweight.owner_id,
          owner_display_name: lightweight.owner_display_name || '',
          tags: lightweight.tags || [],
          allowed_actions: lightweight.allowed_actions,
        }));

        // Build discovery response from cache (for backward compatibility)
        const cachedResponse: DiscoveryResponse = {
          valid_graphs: graphData.valid_graphs,
          invalid_graphs: graphData.invalid_graphs,
          assistants: assistantInfoForDisplay,
          user_role: assistantData.user_role,
          is_dev_admin: assistantData.is_dev_admin,
          scan_metadata: graphData.scan_metadata,
          assistant_counts: assistantData.assistant_counts,
          deployment_id: assistantData.deployment_id,
          deployment_name: assistantData.deployment_name
        };

        // Set discovery data
        setDiscoveryData(cachedResponse);

        // ✅ NEW: Store lightweight agents in state (not full agents!)
        setAgents(lightweightAgents);
        setDisplayItems(mergeGraphsAndAssistants(graphData.valid_graphs, assistantInfoForDisplay, userRole));
        setLoading(false);

        console.log(`[AgentsProvider] ✅ Loaded ${lightweightAgents.length} lightweight agents from cache`);
        return; // ✅ Early return - no API call needed!
      }

      if (graphData) {
        console.log('[AgentsProvider] Partial cache hit (graphs only), will fetch fresh data...');
      }
    }

    // ✅ FRESH DATA FETCHING (cache miss or disabled)

    // Fetch fresh discovery data
    const discoveryResponse = await fetchDiscoveryResponse(deployment.id);
    const response = discoveryResponse.response;

    // Recompute version key post-fetch in case versions changed during request
    await fetchCacheState();
    const freshVersionKey = computeVersionKey();

    // ✅ CACHE BOTH LAYERS
    // Cache graph discovery data (2 hours TTL)
    setGraphDiscoveryCache(userId, {
      valid_graphs: response.valid_graphs,
      invalid_graphs: response.invalid_graphs,
      scan_metadata: response.scan_metadata
    }, freshVersionKey);

    // Cache lightweight assistant list (30 minutes TTL)
    setAssistantListCache(userId, {
      assistants: response.assistants,
      assistant_counts: response.assistant_counts,
      user_role: response.user_role,
      is_dev_admin: response.is_dev_admin,
      deployment_id: response.deployment_id,
      deployment_name: response.deployment_name
    }, freshVersionKey);


    // Extract data from response
    const assistantInfoList = response.assistants;
    const graphs = response.valid_graphs;

    // Set discovery data
    setDiscoveryData(response);

    // Convert AssistantInfo to Agent format for frontend consumption
    const convertedAgents = assistantInfoList.map((item: AssistantInfo) => convertAssistantInfoToAgent(item, deployment.id));

    setAgents(convertedAgents);
    setDisplayItems(mergeGraphsAndAssistants(graphs, assistantInfoList, userRole));
    
    // No per-assistant enrichment
    
    setLoading(false);
  }, [
    session?.accessToken,
    session?.user?.id,
    userRole,
    deployments,
    selectedDeploymentId,
    fetchDiscoveryResponse,
    fetchCacheState,
    computeVersionKey,
    getGraphDiscoveryCache,
    setGraphDiscoveryCache
  ]);

  /**
   * ✅ NEW: Hydrate a lightweight agent to full agent with config/metadata.
   *
   * This function is called when transitioning from list view to operations that
   * need full agent details (starting a chat, editing configuration).
   *
   * Process:
   * 1. Check if agent is already full (using type guard)
   * 2. If lightweight, fetch full details from LangGraph API
   * 3. Convert to full Agent format
   * 4. Update agent in state
   * 5. Return full Agent
   *
   * @param assistantId - ID of the assistant to hydrate
   * @returns Full Agent with config/metadata
   */
  const hydrateAgent = useCallback(async (assistantId: string): Promise<Agent> => {
    // Find the agent in current state
    const agent = agents.find(a => a.assistant_id === assistantId);

    if (!agent) {
      throw new Error(`Agent ${assistantId} not found in state`);
    }

    // If already full, return it
    if (isFullAgent(agent)) {
      console.log(`[AgentsProvider] Agent ${assistantId} already hydrated`);
      return agent;
    }

    console.log(`[AgentsProvider] Hydrating lightweight agent ${assistantId}...`);

    // Fetch full assistant details from LangConnect mirror API
    const apiUrl = `/api/langconnect/agents/mirror/assistants/${assistantId}?ts=${Date.now()}`;
    const response = await fetch(apiUrl, {
      cache: 'no-store',
      headers: {
        Authorization: `Bearer ${session?.accessToken}`,
        'Content-Type': 'application/json',
        'Cache-Control': 'no-cache',
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to hydrate agent: ${response.status} ${errorText}`);
    }

    const fullAssistantData = await response.json();

    // Parse JSONB fields if they're strings (from database)
    const parseJsonField = (field: any) => {
      if (typeof field === 'string') {
        try {
          return JSON.parse(field);
        } catch (error) {
          console.warn(`[AgentsProvider] Failed to parse JSONB field:`, error);
          return {};
        }
      }
      return field || {};
    };

    fullAssistantData.config = parseJsonField(fullAssistantData.config);
    fullAssistantData.metadata = parseJsonField(fullAssistantData.metadata);

    // Convert to full Agent format
    const fullAgent: Agent = {
      ...agent, // Keep lightweight fields
      config: fullAssistantData.config,
      metadata: fullAssistantData.metadata,
      version: fullAssistantData.version || agent.version,
    } as Agent;

    // Remove the _isLightweight flag if it exists
    if ('_isLightweight' in fullAgent) {
      delete (fullAgent as any)._isLightweight;
    }

    // Update agent in state
    setAgents(prevAgents =>
      prevAgents.map(a =>
        a.assistant_id === assistantId ? fullAgent : a
      )
    );

    console.log(`[AgentsProvider] ✅ Hydrated agent ${assistantId}`);
    return fullAgent;
  }, [agents, session?.accessToken]);

  // Track when we've made the first request
  const hasInitiallyLoaded = useRef(false);
  const lastDeploymentId = useRef<string | null>(null);

  // Initial load and refresh when deploymentId changes
  useEffect(() => {
    if (!session?.accessToken) {
      return;
    }

    // Wait for UserRoleProvider to finish loading before starting discovery
    if (roleLoading) {
      return;
    }

    // Wait for role to be validated with a valid session (not a fallback)
    if (!roleValidated) {
      return;
    }

    // Check if this is initial load or deployment changed
    const shouldLoad = !hasInitiallyLoaded.current || 
                      (lastDeploymentId.current !== selectedDeploymentId);

    if (shouldLoad) {
      hasInitiallyLoaded.current = true;
      lastDeploymentId.current = selectedDeploymentId;
      
      setLoading(true);
      loadAgents().finally(() => {
        setLoading(false);
      });
    }
  }, [session?.accessToken, userRole, roleLoading, roleValidated, selectedDeploymentId]); // Removed loadAgents to prevent infinite loop

  // Refresh function
  const refreshAgents = useCallback(async (silent: boolean = false) => {

    if (!session?.accessToken) {
      console.warn("⚠️ No access token found for refreshAgents");
      if (!silent) {
        toast.error("No access token found", {
          richColors: true,
        });
      }
      return;
    }

    try {
      
      setRefreshAgentsLoading(true);

      // Force true cache bypass for refresh
      await loadAgents(false); // FALSE = bypass cache completely
      
      if (!silent) {
        const message = agentMessages.refresh.success();
        notify.success(message.title, {
          description: message.description,
          key: message.key,
        });
      }
    } catch (e) {
      console.error("❌ Failed to refresh agents:", e);
      if (!silent) {
        const message = agentMessages.refresh.error(e instanceof Error ? e.message : 'Unknown error');
        notify.error(message.title, {
          description: message.description,
          key: message.key,
        });
      }
    } finally {
      setRefreshAgentsLoading(false);
    }
  }, [session?.accessToken, loadAgents]);

  // Function to manually add an agent to the list for immediate UI updates
  const addAgentToList = useCallback((newAgent: Agent | LightweightAgent) => {

    // ✅ UPDATED: Handle both lightweight and full agents
    let optimisticAgent: Agent | LightweightAgent;

    if (isFullAgent(newAgent)) {
      // Add optimistic creation timestamp to full agents
      optimisticAgent = {
        ...newAgent,
        metadata: {
          ...newAgent.metadata,
          optimistic_created_at: Date.now()
        }
      };
    } else {
      // Lightweight agents don't have metadata field
      optimisticAgent = newAgent;
    }

    // Add to agents array
    setAgents(prevAgents => {

      // Check if agent already exists to avoid duplicates
      const exists = prevAgents.some(a => a.assistant_id === newAgent.assistant_id);
      if (exists) {
        return prevAgents;
      }

      const newAgents = [...prevAgents, optimisticAgent];

      // Force React to re-render by returning a new reference
      return newAgents;
    });
    
    // Also update display items
    setDisplayItems(prevItems => {
      
      const exists = prevItems.some(item => 
        item.type === 'assistant' && item.assistant_id === optimisticAgent.assistant_id
      );
      if (exists) {
        return prevItems;
      }
      
      // Create display item for the new agent
      // ✅ UPDATED: Handle both lightweight (has description field) and full agents (description in metadata)
      const description = isLightweightAgent(optimisticAgent)
        ? optimisticAgent.description || ""
        : (typeof (optimisticAgent.metadata as any)?.description === 'string' ? (optimisticAgent.metadata as any).description : optimisticAgent.description) || "";

      const newDisplayItem: AgentDisplayItem = {
        id: `assistant_${optimisticAgent.assistant_id}`,
        type: "assistant",
        name: optimisticAgent.name,
        description: description,
        assistant_id: optimisticAgent.assistant_id,
        graph_id: optimisticAgent.graph_id,
        permission_level: optimisticAgent.permission_level || "owner",
        owner_id: optimisticAgent.owner_id || session?.user?.id || "",
        owner_display_name: optimisticAgent.owner_display_name || session?.user?.email || "You",
        created_at: optimisticAgent.created_at,
        updated_at: optimisticAgent.updated_at,
      };
      
      const newDisplayItems = [...prevItems, newDisplayItem];
      
      return newDisplayItems;
    });
    
  }, [session?.user?.id, session?.user?.email]);

  const agentsContextValue: AgentsContextType = useMemo(() => ({
    agents,
    displayItems,
    refreshAgents,
    loading,
    refreshAgentsLoading,
    discoveryData,
    error,
    getGraphPermissionLevel: (graphId: string) => {
      const graph = discoveryData?.valid_graphs?.find(g => g.graph_id === graphId);
      const permissionLevel = graph?.user_permission_level as "admin" | "access" | null;
      
      return permissionLevel;
    },
    invalidateDiscoveryCache: (userId?: string, deploymentId?: string) => {
      const userIdToInvalidate = userId || session?.user?.id;
      if (userIdToInvalidate) {
        invalidateDiscoveryCache(userIdToInvalidate);
      }
    },
    invalidateAssistantCaches,
    invalidateAllAssistantCaches,
    // ✅ NEW: Layered cache invalidation methods
    invalidateGraphDiscoveryCache: (userId?: string) => {
      const userIdToInvalidate = userId || session?.user?.id;
      if (userIdToInvalidate) {
        invalidateGraphDiscoveryCache(userIdToInvalidate);
      }
    },
    invalidateAssistantListCache: (userId?: string) => {
      const userIdToInvalidate = userId || session?.user?.id;
      if (userIdToInvalidate) {
        invalidateAssistantListCache(userIdToInvalidate);
      }
    },
    invalidateEnhancementStatusCache: (userId?: string) => {
      const userIdToInvalidate = userId || session?.user?.id;
      if (userIdToInvalidate) {
        invalidateEnhancementStatusCache(userIdToInvalidate);
      }
    },
    debugCacheState: () => {
      const userId = session?.user?.id;

      if (userId) {
        // Check graph cache layer only (assistant caching disabled)
        const graphCache = getGraphDiscoveryCache(userId, computeVersionKey());

        if (graphCache) {
          console.log('[AgentsProvider] Graph cache exists:', {
            graphCount: graphCache.valid_graphs.length,
            version: computeVersionKey()
          });
        } else {
          console.log('[AgentsProvider] No graph cache found');
        }
      }

      // List all cache keys in localStorage
      const cacheKeys = Object.keys(localStorage).filter(key =>
        key.includes('agents_') || key.includes('assistant_') || key.includes('enriched_')
      );
      if (cacheKeys.length > 0) {
        console.log('[AgentsProvider] Cache keys in localStorage:', cacheKeys);
      }
    },
    addAgentToList,
    hydrateAgent,
    defaultAssistant,
    defaultAssistantLoading: defaultLoading,
    setDefaultAssistant,
    clearDefaultAssistant,
    refreshDefaultAssistant,
  }), [
    agents,
    displayItems,
    refreshAgents,
    loading,
    refreshAgentsLoading,
    discoveryData,
    error,
    session?.user?.id,
    invalidateDiscoveryCache,
    invalidateAssistantCaches,
    invalidateAllAssistantCaches,
    invalidateGraphDiscoveryCache,
    invalidateAssistantListCache,
    getGraphDiscoveryCache,
    computeVersionKey,
    addAgentToList,
    hydrateAgent,
    defaultAssistant,
    defaultLoading,
    setDefaultAssistant,
    clearDefaultAssistant,
    refreshDefaultAssistant,
  ]);

  return (
    <AgentsContext.Provider value={agentsContextValue}>
      {children}
    </AgentsContext.Provider>
  );
};

// Create a custom hook to use the context
export const useAgentsContext = (): AgentsContextType => {
  const context = useContext(AgentsContext);
  if (context === undefined) {
    throw new Error("useAgentsContext must be used within a AgentsProvider");
  }
  return context;
};

export default AgentsContext;