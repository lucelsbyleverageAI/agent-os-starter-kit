import { useEffect, useState } from "react";
import { useQueryState } from "nuqs";
import { useAgentsContext } from "@/providers/Agents";
import { useAuthContext } from "@/providers/Auth";
import { isUserSpecifiedDefaultAgent, isPrimaryAssistant } from "@/lib/agent-utils";
import { getDeployments } from "@/lib/environment/deployments";

/**
 * Hook to handle default agent selection logic.
 * This runs early in the component tree to set agentId/deploymentId
 * before components that depend on them render.
 * 
 * @returns Object with loading state information
 */
export function useDefaultAgentSelection() {
  const { agents, loading, error, defaultAssistant, defaultAssistantLoading } = useAgentsContext();
  const [agentId, setAgentId] = useQueryState("agentId");
  const [deploymentId, setDeploymentId] = useQueryState("deploymentId");
  const { isLoading: authLoading } = useAuthContext();
  const [lastError, setLastError] = useState<string | null>(null);

  // Only select default agent once, after loading is complete
  useEffect(() => {
    if (agentId || deploymentId) return;
    if (loading || authLoading || defaultAssistantLoading) return;
    if (agents.length === 0) {
      setLastError(error ? `Failed to load agents: ${error}` : null);
      return;
    }

    const deployments = getDeployments();
    const defaultDeployment = deployments.find((d) => d.isDefault);
    if (!defaultDeployment) {
      setLastError("No default deployment configured");
      return;
    }

    // First priority: User's database-backed default assistant
    if (defaultAssistant) {
      const dbDefaultAgent = agents.find(
        (agent) => agent.assistant_id === defaultAssistant.assistant_id
      );
      if (dbDefaultAgent) {
        setAgentId(dbDefaultAgent.assistant_id);
        setDeploymentId(dbDefaultAgent.deploymentId);
        setLastError(null);
        return;
      }
    }

    // Second priority: User-specified default agent (metadata-based, legacy)
    const defaultAgent = agents.find(isUserSpecifiedDefaultAgent);
    if (defaultAgent) {
      setAgentId(defaultAgent.assistant_id);
      setDeploymentId(defaultAgent.deploymentId);
      setLastError(null);
      return;
    }

    // Third priority: Primary assistant
    const primaryAgent = agents.find(isPrimaryAssistant);
    if (primaryAgent) {
      setAgentId(primaryAgent.assistant_id);
      setDeploymentId(primaryAgent.deploymentId);
      setLastError(null);
      return;
    }

    // Final fallback: use any available agent
    if (agents.length > 0) {
      const fallbackAgent = agents[0];
      setAgentId(fallbackAgent.assistant_id);
      setDeploymentId(fallbackAgent.deploymentId);
      setLastError(null);
      return;
    }
    setLastError("No suitable agents found");
  }, [agents, loading, authLoading, defaultAssistantLoading, defaultAssistant, agentId, deploymentId, setAgentId, setDeploymentId, error]);

  return {
    isLoading: loading || defaultAssistantLoading,
    isAuthLoading: authLoading,
    hasAgents: agents.length > 0,
    hasUrlParams: !!(agentId || deploymentId),
    error: lastError,
    // Retry only if there was a network/backend error
    retry: () => {
      setLastError(null);
      window.location.reload();
    }
  };
} 