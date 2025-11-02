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

// EnhancementStatusCache removed

// Per-assistant cache interfaces removed

type AgentsContextType = {
  /**
   * Array of agents with permission metadata
   */
  agents: Agent[];
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
  addAgentToList: (agent: Agent) => void;
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

  const [agents, setAgents] = useState<Agent[]>([]);
  const [displayItems, setDisplayItems] = useState<AgentDisplayItem[]>([]);
  const [discoveryData, setDiscoveryData] = useState<DiscoveryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const _firstRequestMade = useRef(false);
  const [loading, setLoading] = useState(false);
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
   * Assistant list caching disabled to avoid localStorage quota issues.
   * Backend ETag caching (3-min TTL) provides sufficient performance.
   *
   * @deprecated Kept for backward compatibility - always returns null
   */
  const getAssistantListCache = useCallback((_userId: string, _expectedVersion: string): AssistantListCache | null => {
    return null;
  }, []);

  /**
   * Assistant list caching disabled to avoid localStorage quota issues.
   * Backend ETag caching (3-min TTL) provides sufficient performance.
   *
   * @deprecated Kept for backward compatibility - does nothing
   */
  const setAssistantListCache = useCallback((_userId: string, _assistantData: { assistants: AssistantInfo[]; assistant_counts: any; user_role: string; is_dev_admin: boolean; deployment_id: string; deployment_name: string }, _versionKey: string) => {
    // No-op: caching disabled
  }, []);

  /**
   * Assistant list caching disabled - kept for backward compatibility.
   *
   * @deprecated Does nothing since caching is disabled
   */
  const invalidateAssistantListCache = useCallback((_userId: string) => {
    // No-op: caching disabled
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

      // Check Graph Discovery Cache (2 hours TTL)
      // Note: Assistant list caching disabled to avoid localStorage quota issues
      // Backend ETag caching (3-min TTL) provides sufficient performance for assistants
      const graphData = getGraphDiscoveryCache(userId, versionKey);

      if (graphData) {
        console.log('[AgentsProvider] Using cached graph data, fetching fresh assistant data...');
        // We have graph cache, but will fetch fresh assistant data from backend
        // This leverages backend ETag caching without localStorage overhead
      }
    }

    // ✅ FRESH DATA FETCHING WITH LAYERED CACHING

    // Fetch fresh discovery data
    const discoveryResponse = await fetchDiscoveryResponse(deployment.id);
    const response = discoveryResponse.response;

    // Recompute version key post-fetch in case versions changed during request
    await fetchCacheState();
    const freshVersionKey = computeVersionKey();

    // ✅ CACHE GRAPH DISCOVERY DATA
    // Cache graph discovery data (2 hours TTL)
    // Note: Assistant list caching disabled to avoid localStorage quota issues
    setGraphDiscoveryCache(userId, {
      valid_graphs: response.valid_graphs,
      invalid_graphs: response.invalid_graphs,
      scan_metadata: response.scan_metadata
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
  const addAgentToList = useCallback((newAgent: Agent) => {
    
    // Add optimistic creation timestamp to help preserve recent agents
    const optimisticAgent = {
      ...newAgent,
      metadata: {
        ...newAgent.metadata,
        optimistic_created_at: Date.now()
      }
    };
    
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
      const newDisplayItem: AgentDisplayItem = {
        id: `assistant_${optimisticAgent.assistant_id}`,
        type: "assistant",
        name: optimisticAgent.name,
        description: (typeof (optimisticAgent.metadata as any)?.description === 'string' ? (optimisticAgent.metadata as any).description : "") || "",
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