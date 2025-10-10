"use client";

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


/**
 * Merge graphs and assistants into a unified display format
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
 * Convert AgentDisplayItem back to legacy Agent format for backward compatibility
 */
function _convertToLegacyAgent(item: AgentDisplayItem, deploymentId: string): Agent {
  return {
    assistant_id: item.assistant_id || item.id,
    graph_id: item.graph_id,
    name: item.name,
    description: item.description || undefined,
    config: {},
    metadata: item.metadata || {},
    created_at: item.created_at || new Date().toISOString(),
    updated_at: item.updated_at || item.created_at || new Date().toISOString(),
    version: 1,
    deploymentId,
    supportedConfigs: item.supportedConfigs,
    permission_level: item.permission_level,
    owner_id: item.owner_id,
    owner_display_name: item.owner_display_name,
    type: item.type,
    needs_initialization: item.needs_initialization,
    schema_accessible: item.schema_accessible,
  };
}

/**
 * Convert AssistantInfo from discovery response to legacy Agent format for backward compatibility
 */
function convertAssistantInfoToLegacyAgent(item: AssistantInfo, deploymentId: string): Agent {
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
    owner_id: item.owner_id,
    owner_display_name: item.owner_display_name,
    type: "assistant",
    needs_initialization: false,
    schema_accessible: true,
  };
}

// ✅ LAYERED CACHING CONFIGURATION
// Layer 1: Graph Discovery Cache (LONG-LIVED - graphs rarely change)
const GRAPH_DISCOVERY_CACHE_DURATION = 2 * 60 * 60 * 1000; // 2 hours
const GRAPH_DISCOVERY_CACHE_KEY_PREFIX = 'agents_graph_discovery_';

// Layer 2: Assistant List Cache (MEDIUM-LIVED - assistants change occasionally)
const ASSISTANT_LIST_CACHE_DURATION = 30 * 60 * 1000; // 30 minutes
const ASSISTANT_LIST_CACHE_KEY_PREFIX = 'agents_assistant_list_';

// Per-assistant caches removed for simplification

// ✅ LAYERED CACHE INTERFACES
interface GraphDiscoveryCache {
  valid_graphs: GraphInfo[];
  invalid_graphs: GraphInfo[];
  scan_metadata: any;
  timestamp: number;
  userId: string;
  version: string;
}

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
  
  const [agents, setAgents] = useState<Agent[]>([]);
  const [displayItems, setDisplayItems] = useState<AgentDisplayItem[]>([]);
  const [discoveryData, setDiscoveryData] = useState<DiscoveryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const _firstRequestMade = useRef(false);
  const [loading, setLoading] = useState(false);
  const [refreshAgentsLoading, setRefreshAgentsLoading] = useState(false);

  // Cache configuration
      const _AGENTS_CACHE_KEY = 'oap_agents_cache';
    const _AGENTS_CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

  // Version-aware cache state
  const [graphsVersion, setGraphsVersion] = useState<number | null>(null);
  const [assistantsVersion, setAssistantsVersion] = useState<number | null>(null);
  const [schemasVersion, setSchemasVersion] = useState<number | null>(null);

  const computeVersionKey = useCallback(() => {
    const g = graphsVersion ?? 0;
    const a = assistantsVersion ?? 0;
    const s = schemasVersion ?? 0;
    return `g${g}-a${a}-s${s}`;
  }, [graphsVersion, assistantsVersion, schemasVersion]);

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
      // ignore; fallback to TTL
    }
  }, [session?.accessToken]);

  useEffect(() => {
    // Poll cache state occasionally for version-aware invalidation
    if (!session?.accessToken) return;
    
    fetchCacheState();
    const interval = setInterval(fetchCacheState, 30000); // Poll every 30 seconds
    return () => clearInterval(interval);
  }, [session?.accessToken]); // Only depend on accessToken, not fetchCacheState

  // ✅ LAYERED CACHE UTILITIES (version-aware)

  // Layer 1: Graph Discovery Cache Utilities
  const getGraphDiscoveryCache = useCallback((userId: string, expectedVersion: string): GraphDiscoveryCache | null => {
    try {
      const cached = localStorage.getItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`);
      if (!cached) return null;
      const data = JSON.parse(cached) as GraphDiscoveryCache;
      const now = Date.now();
      if (now - data.timestamp > GRAPH_DISCOVERY_CACHE_DURATION) {
        localStorage.removeItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`);
        return null;
      }
      if (!data.version || data.version !== expectedVersion) {
        // Invalidate silently if backend versions changed
        localStorage.removeItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`);
        return null;
      }
      return data;
    } catch (error) {
      console.warn('Failed to read graph discovery cache:', error);
      return null;
    }
  }, []);

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
    } catch (error) {
      console.warn('Failed to write graph discovery cache:', error);
    }
  }, []);

  const invalidateGraphDiscoveryCache = useCallback((userId: string) => {
    try {
      localStorage.removeItem(`${GRAPH_DISCOVERY_CACHE_KEY_PREFIX}${userId}`);
    } catch (error) {
      console.warn('Failed to invalidate graph discovery cache:', error);
    }
  }, []);

  // Layer 2: Assistant List Cache Utilities
  const getAssistantListCache = useCallback((userId: string, expectedVersion: string): AssistantListCache | null => {
    try {
      const cacheKey = `${ASSISTANT_LIST_CACHE_KEY_PREFIX}${userId}`;
      const cached = localStorage.getItem(cacheKey);
      if (!cached) {
        return null;
      }
      const data = JSON.parse(cached) as AssistantListCache;
      const now = Date.now();
      if (now - data.timestamp > ASSISTANT_LIST_CACHE_DURATION) {
        localStorage.removeItem(cacheKey);
        return null;
      }
      if (!data.version || data.version !== expectedVersion) {
        localStorage.removeItem(cacheKey);
        return null;
      }
      return data;
    } catch (error) {
      console.warn('Failed to read assistant list cache:', error);
      return null;
    }
  }, []);

  const setAssistantListCache = useCallback((userId: string, assistantData: { assistants: AssistantInfo[]; assistant_counts: any; user_role: string; is_dev_admin: boolean; deployment_id: string; deployment_name: string }, versionKey: string) => {
    try {
      const cacheData: AssistantListCache = {
        assistants: assistantData.assistants,
        assistant_counts: assistantData.assistant_counts,
        user_role: assistantData.user_role,
        is_dev_admin: assistantData.is_dev_admin,
        deployment_id: assistantData.deployment_id,
        deployment_name: assistantData.deployment_name,
        timestamp: Date.now(),
        userId,
        version: versionKey,
      };
      localStorage.setItem(`${ASSISTANT_LIST_CACHE_KEY_PREFIX}${userId}`, JSON.stringify(cacheData));
    } catch (error) {
      console.warn('Failed to write assistant list cache:', error);
    }
  }, []);

  const invalidateAssistantListCache = useCallback((userId: string) => {
    try {
      localStorage.removeItem(`${ASSISTANT_LIST_CACHE_KEY_PREFIX}${userId}`);
    } catch (error) {
      console.warn('Failed to invalidate assistant list cache:', error);
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

      // Layer 1: Check Graph Discovery Cache (2 hours)
      const graphData = getGraphDiscoveryCache(userId, versionKey);
      
      // Layer 2: Check Assistant List Cache (30 minutes)
      const assistantData = getAssistantListCache(userId, versionKey);
      
      // If we have both core layers cached, we can use them
      if (graphData && assistantData) {
        console.log('[AgentsProvider] Using cached data', {
          graphsCount: graphData.valid_graphs?.length || 0,
          assistantsCount: assistantData.assistants?.length || 0,
          graphData: graphData.valid_graphs,
          cacheVersion: versionKey
        });

        // Reconstruct discovery response from cached layers
        const reconstructedResponse: DiscoveryResponse = {
          valid_graphs: graphData.valid_graphs,
          invalid_graphs: graphData.invalid_graphs,
          assistants: assistantData.assistants,
          user_role: assistantData.user_role as 'dev_admin' | 'business_admin' | 'user',
          is_dev_admin: assistantData.is_dev_admin,
          scan_metadata: graphData.scan_metadata,
          assistant_counts: assistantData.assistant_counts,
          deployment_id: assistantData.deployment_id,
          deployment_name: assistantData.deployment_name
        };

        console.log('[AgentsProvider] Reconstructed discovery response', {
          valid_graphs_count: reconstructedResponse.valid_graphs?.length || 0,
          valid_graphs: reconstructedResponse.valid_graphs
        });

        // Set discovery data
        setDiscoveryData(reconstructedResponse);
        
        // Convert to legacy Agent format for backward compatibility
        const convertedAgents = assistantData.assistants.map((item: AssistantInfo) => convertAssistantInfoToLegacyAgent(item, deployment.id));
        
        setAgents(convertedAgents);
        setDisplayItems(mergeGraphsAndAssistants(graphData.valid_graphs, assistantData.assistants, assistantData.user_role));
        
        // No per-assistant enrichment
        
        setLoading(false);
        return;
      }
    }

    // ✅ FRESH DATA FETCHING WITH LAYERED CACHING

    // Fetch fresh discovery data
    const discoveryResponse = await fetchDiscoveryResponse(deployment.id);
    const response = discoveryResponse.response;

    console.log('[AgentsProvider] Fresh API response received', {
      valid_graphs_count: response.valid_graphs?.length || 0,
      valid_graphs: response.valid_graphs,
      assistants_count: response.assistants?.length || 0,
      deployment: deployment.id,
      duration: discoveryResponse.duration
    });

    // Recompute version key post-fetch in case versions changed during request
    await fetchCacheState();
    const freshVersionKey = computeVersionKey();

    // ✅ CACHE IN LAYERS
    // Layer 1: Cache graph discovery data (2 hours)
    console.log('[AgentsProvider] Caching graph discovery data', {
      graphsCount: response.valid_graphs?.length || 0,
      versionKey: freshVersionKey,
      graphIds: response.valid_graphs?.map(g => g.graph_id) || []
    });
    setGraphDiscoveryCache(userId, {
      valid_graphs: response.valid_graphs,
      invalid_graphs: response.invalid_graphs,
      scan_metadata: response.scan_metadata
    }, freshVersionKey);

    // Layer 2: Cache assistant list data (30 minutes)
    console.log('[AgentsProvider] Caching assistant list data', {
      assistantsCount: response.assistants?.length || 0,
      versionKey: freshVersionKey
    });
    setAssistantListCache(userId, {
      assistants: response.assistants,
      assistant_counts: response.assistant_counts,
      user_role: response.user_role,
      is_dev_admin: response.is_dev_admin,
      deployment_id: response.deployment_id,
      deployment_name: response.deployment_name
    }, freshVersionKey);
    
    // Set agents from response
    const legacyAgents = response.assistants;
    const graphs = response.valid_graphs;
    
    // Set discovery data
    setDiscoveryData(response);
    
    // Convert to legacy Agent format for backward compatibility
    const convertedAgents = legacyAgents.map((item: AssistantInfo) => convertAssistantInfoToLegacyAgent(item, deployment.id));
    
    setAgents(convertedAgents);
    setDisplayItems(mergeGraphsAndAssistants(graphs, legacyAgents.map(item => item as AssistantInfo), userRole));
    
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
    getAssistantListCache,
    setGraphDiscoveryCache,
    setAssistantListCache
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
        // Check all cache layers
        const _graphCache = getGraphDiscoveryCache(userId, computeVersionKey());
        const assistantCache = getAssistantListCache(userId, computeVersionKey());
        
        
        if (assistantCache) {
          assistantCache.assistants.forEach(a => console.log(`    * ${a.name} (${a.assistant_id}) - ${a.permission_level}`));
        }
      }
      
      // List all cache keys in localStorage
      Object.keys(localStorage).forEach(key => {
        if (key.includes('agents_') || key.includes('assistant_') || key.includes('enriched_')) {
          // Debug cache keys (console logging removed for performance)
        }
      });
    },
    addAgentToList,
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
    getAssistantListCache,
    computeVersionKey,
    addAgentToList
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