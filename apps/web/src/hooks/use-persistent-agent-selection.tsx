import { useEffect } from "react";
import { useQueryState } from "nuqs";

const LAST_AGENT_KEY = 'oap_last_selected_agent';

interface LastAgent {
  agentId: string;
  deploymentId: string;
  timestamp: number;
}

/**
 * Hook to persist and restore the user's last selected agent
 * This helps avoid the "No Agent Available" issue on navigation
 */
export function usePersistentAgentSelection() {
  const [agentId, setAgentId] = useQueryState("agentId");
  const [deploymentId, setDeploymentId] = useQueryState("deploymentId");

  // Save agent selection when it changes
  useEffect(() => {
    if (agentId && deploymentId) {
      const lastAgent: LastAgent = {
        agentId,
        deploymentId,
        timestamp: Date.now()
      };
      
      try {
        localStorage.setItem(LAST_AGENT_KEY, JSON.stringify(lastAgent));
      } catch (e) {
        console.warn('Failed to save last agent selection:', e);
      }
    }
  }, [agentId, deploymentId]);

  // Restore last agent if no current selection
  const restoreLastAgent = () => {
    if (agentId || deploymentId) return false; // Already have an agent selected

    try {
      const saved = localStorage.getItem(LAST_AGENT_KEY);
      if (saved) {
        const lastAgent: LastAgent = JSON.parse(saved);
        
        // Only restore if saved within last 24 hours
        const isRecent = Date.now() - lastAgent.timestamp < 24 * 60 * 60 * 1000;
        
        if (isRecent && lastAgent.agentId && lastAgent.deploymentId) {
          setAgentId(lastAgent.agentId);
          setDeploymentId(lastAgent.deploymentId);
          return true;
        }
      }
    } catch (e) {
      console.warn('Failed to restore last agent selection:', e);
    }
    
    return false;
  };

  const clearLastAgent = () => {
    try {
      localStorage.removeItem(LAST_AGENT_KEY);
    } catch (e) {
      console.warn('Failed to clear last agent selection:', e);
    }
  };

  return {
    restoreLastAgent,
    clearLastAgent,
    hasLastAgent: () => {
      try {
        const saved = localStorage.getItem(LAST_AGENT_KEY);
        return !!saved;
      } catch {
        return false;
      }
    }
  };
} 