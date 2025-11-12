"use client";

import React, {
  createContext,
  useContext,
  PropsWithChildren,
  useEffect,
  useRef,
  useState,
  useCallback,
} from "react";
import useMCP from "../hooks/use-mcp";
import { useAuthContext } from "./Auth";
import { Tool, Toolkit } from "@/types/tool";

type MCPContextType = ReturnType<typeof useMCP> & { 
  loading: boolean;
  refreshTools: () => Promise<void>;
};

export const MCPContext = createContext<MCPContextType | null>(null);

// Cache configuration
const TOOLS_CACHE_KEY = 'oap_tools_cache';
const TOOLS_CACHE_DURATION = 60 * 60 * 1000; // 1 hour

interface ToolsCache {
  tools: Tool[];
  toolkits: Toolkit[];
  timestamp: number;
  cursor: string;
}

export const MCPProvider: React.FC<PropsWithChildren> = ({ children }) => {
  const { isAuthenticated, isLoading: authLoading } = useAuthContext();
  const mcpState = useMCP({
    name: "Tools Interface",
    version: "1.0.0",
  });
  const firstRequestMade = useRef(false);
  const [loading, setLoading] = useState(true); // Start as true to show loading state on initial render

  // Group tools by toolkit with memoization
  const groupToolsByToolkit = useCallback((tools: Tool[]): Toolkit[] => {
    const grouped = tools.reduce((acc, tool) => {
      const toolkitName = tool.toolkit || 'uncategorized';
      const toolkitDisplayName = tool.toolkit_display_name || 'Uncategorised';
      
      if (!acc[toolkitName]) {
        acc[toolkitName] = {
          name: toolkitName,
          display_name: toolkitDisplayName,
          tools: [],
          count: 0,
        };
      }
      
      acc[toolkitName].tools.push(tool);
      acc[toolkitName].count++;
      return acc;
    }, {} as Record<string, Toolkit>);
    
    return Object.values(grouped).sort((a, b) => 
      a.display_name.localeCompare(b.display_name)
    );
  }, []);

  // Cache management functions
  const getCachedTools = useCallback((): ToolsCache | null => {
    try {
      const cached = localStorage.getItem(TOOLS_CACHE_KEY);
      if (cached) {
        const cacheData = JSON.parse(cached) as ToolsCache;
        if (Date.now() - cacheData.timestamp < TOOLS_CACHE_DURATION) {
          return cacheData;
        }
      }
    } catch (_e) {
      // Failed to read tools cache
    }
    return null;
  }, []);

  const setCachedTools = useCallback((tools: Tool[], toolkits: Toolkit[], cursor: string) => {
    try {
      const cacheData: ToolsCache = {
        tools,
        toolkits,
        timestamp: Date.now(),
        cursor,
      };
      localStorage.setItem(TOOLS_CACHE_KEY, JSON.stringify(cacheData));
    } catch (_e) {
      // Failed to cache tools
    }
  }, []);

  const loadTools = useCallback(async (useCache: boolean = true) => {
    if (!isAuthenticated) return;

    // Try to load from cache first
    if (useCache) {
      const cachedData = getCachedTools();
      if (cachedData) {
        // Use cache if it's less than 5 minutes old
        if (cachedData && (Date.now() - cachedData.timestamp) < 5 * 60 * 1000) {
          mcpState.setTools(cachedData.tools);
          mcpState.setToolkits(cachedData.toolkits);
          setLoading(false);
          return;
        }
      }
    }

    try {
              setLoading(true);
        
        const tools = await mcpState.getTools();
      
      
      mcpState.setTools(tools);
      
      // Group tools into toolkits
      const groupedToolkits = groupToolsByToolkit(tools);
      mcpState.setToolkits(groupedToolkits);
      
      // Cache the results
      setCachedTools(tools, groupedToolkits, mcpState.cursor);
      
          } catch (error) {
      
      
      // Only log non-authentication errors
      const errorMessage = error instanceof Error ? error.message : '';
      if (errorMessage.includes('401') || errorMessage.includes('Unauthorized')) {
        // Silently ignore authentication errors
      } else {
        // Log other errors silently for now
      }
      // Reset flag so it can retry later
      firstRequestMade.current = false;
      throw error;
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, mcpState, getCachedTools, setCachedTools]);

  const refreshTools = useCallback(async () => {
    await loadTools(false); // Force refresh, bypass cache
  }, [loadTools]);

  useEffect(() => {
    // Only load tools if user is authenticated and not currently loading auth
    if (!isAuthenticated || authLoading) return;
    if (mcpState.tools.length || firstRequestMade.current) return;

    firstRequestMade.current = true;
    loadTools(true); // Use cache on initial load
  }, [isAuthenticated, authLoading, mcpState.tools.length, loadTools]);

  return (
    <MCPContext.Provider value={{ ...mcpState, loading, refreshTools }}>
      {children}
    </MCPContext.Provider>
  );
};

export const useMCPContext = () => {
  const context = useContext(MCPContext);
  if (context === null) {
    throw new Error("useMCPContext must be used within a MCPProvider");
  }
  return context;
};

export const useOptionalMCPContext = () => {
  return useContext(MCPContext);
};
