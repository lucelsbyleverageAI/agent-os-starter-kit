import { ToolComponent, ToolRegistryEntry, ToolRegistry } from "../types";
import {
  SilentToolCall,
  SimpleToolCall,
  ResearchProgressTool,
  FinalResearchReportTool,
  PublishFileTool,
  SandboxInitializationTool,
  TaskTool,
} from "./components";
// Unused imports removed

// Registry key structure: "graphId:toolName" or "*:toolName" for global
// Also supports prefix patterns like "*:search_collection_*" for tool name patterns
export const TOOL_REGISTRY: ToolRegistry = {
  
  // Research progress tracking tool
  "*:research_progress_tracking": {
    component: ResearchProgressTool,
  },
  
  // Final research report tool
  "*:final_research_report": {
    component: FinalResearchReportTool,
  },

  // Skills DeepAgent file publishing tool
  "*:publish_file_to_user": {
    component: PublishFileTool,
  },

  // Skills DeepAgent sandbox initialization status indicator
  // Shows loading UI during sandbox creation, disappears when complete
  "*:sandbox_initialization": {
    component: SandboxInitializationTool,
  },

  // Skills DeepAgent task delegation tool
  // Shows sub-agent delegation with slide-over panel for response
  "*:task": {
    component: TaskTool,
  },

  // Example: Global tools (available for all graphs)
  // "*:arcade_CodeSandbox_RunCode": {
  //   component: SimpleToolCall,
  // },
  
  // Example: Graph-specific tools (using graph_id)
  // "loreal_agent:web_search": {
  //   component: LorealWebSearchTool,  // Custom UI for L'Oreal agent
  // },
  
  // Example: Silent tools (never render)
  "*:internal_logging": {
    component: SilentToolCall,
    silent: true,
  },
  
  "*:debug_tool": {
    component: SilentToolCall,
    silent: true,
  },
  
    // Deep research agent - silent query generation tools
    "*:generate_queries": {
      component: SilentToolCall,
      silent: true,
    },

    "*:generate_sections": {
      component: SilentToolCall,
      silent: true,
    },
};

export const DEFAULT_TOOL_COMPONENT = SimpleToolCall;

/**
 * Get the appropriate tool component for a given tool name and graph
 * @param toolName - The name of the tool being called
 * @param graphId - The graph ID of the current assistant (human-readable)
 * @param hideToolCallsToggle - Whether the hide tool calls toggle is enabled
 * @returns The component to render, or null if tool should be hidden
 */
export function getToolComponent(
  toolName: string, 
  graphId: string,
  hideToolCallsToggle: boolean
): ToolComponent | null {
  // Helper function to find pattern matches
  const findPatternMatch = (prefix: string): ToolRegistryEntry | undefined => {
    // First try exact match
    const exactMatch = TOOL_REGISTRY[`${prefix}:${toolName}`];
    if (exactMatch) {
      return exactMatch;
    }
    
    // Then try pattern matches
    for (const [key, entry] of Object.entries(TOOL_REGISTRY)) {
      if (key.startsWith(`${prefix}:`) && key.endsWith('*')) {
        const pattern = key.slice(prefix.length + 1, -1); // Remove prefix: and trailing *
        if (toolName.startsWith(pattern)) {
          return entry;
        }
      }
    }
    
    return undefined;
  };

  // Check for silent tools first (both exact and pattern matches)
  const silentEntry = findPatternMatch(graphId) || findPatternMatch('*');
  
  if (silentEntry?.silent) {
    return null; // Never render silent tools
  }
  
  // If hide toggle is on, don't render any tools (except we already handled silent)
  if (hideToolCallsToggle) {
    return null;
  }
  
  // Look for graph-specific component first (exact and pattern)
  const graphSpecific = findPatternMatch(graphId);
  if (graphSpecific) {
    return graphSpecific.component;
  }
  
  // Fall back to global component (exact and pattern)
  const globalTool = findPatternMatch('*');
  if (globalTool) {
    return globalTool.component;
  }
  
  // Fall back to default
  return DEFAULT_TOOL_COMPONENT;
}

/**
 * Check if a tool should be silent (never render)
 * @param toolName - The name of the tool
 * @param graphId - The graph ID of the current assistant (human-readable)
 * @returns True if the tool should be silent
 */
export function isSilentTool(toolName: string, graphId: string): boolean {
  // Helper function to find pattern matches (reuse logic from getToolComponent)
  const findPatternMatch = (prefix: string): ToolRegistryEntry | undefined => {
    // First try exact match
    const exactMatch = TOOL_REGISTRY[`${prefix}:${toolName}`];
    if (exactMatch) {
      return exactMatch;
    }
    
    // Then try pattern matches
    for (const [key, entry] of Object.entries(TOOL_REGISTRY)) {
      if (key.startsWith(`${prefix}:`) && key.endsWith('*')) {
        const pattern = key.slice(prefix.length + 1, -1); // Remove prefix: and trailing *
        if (toolName.startsWith(pattern)) {
          return entry;
        }
      }
    }
    
    return undefined;
  };

  const graphSpecific = findPatternMatch(graphId);
  const global = findPatternMatch('*');
  
  return graphSpecific?.silent || global?.silent || false;
}

/**
 * Get all registered tool names for debugging/inspection
 */
export function getRegisteredTools(): string[] {
  return Object.keys(TOOL_REGISTRY);
}

/**
 * Get all tools registered for a specific graph
 */
export function getGraphTools(graphId: string): string[] {
  return Object.keys(TOOL_REGISTRY)
    .filter(key => key.startsWith(`${graphId}:`))
    .map(key => key.split(':')[1]);
}

// Export shared components for use in custom tools
export * from "./shared";
export * from "./components"; 