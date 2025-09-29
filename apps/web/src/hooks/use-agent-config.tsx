import {
  ConfigurableFieldAgentsMetadata,
  ConfigurableFieldMCPMetadata,
  ConfigurableFieldRAGMetadata,
  ConfigurableFieldUIMetadata,
} from "@/types/configurable";
import { useCallback, useState } from "react";
import { useAgents } from "./use-agents";
import {
  extractConfigurationsFromAgent,
  getConfigurableDefaults,
} from "@/lib/ui-config";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { Agent, InputMode } from "@/types/agent";
import { GraphSchema } from "@langchain/langgraph-sdk";
import { useQueryState } from "nuqs";

/**
 * A custom hook for managing and accessing the configurable
 * fields on an agent.
 */
// Simple in-flight deduplication across components for the same agent
const inflightLoads = new Map<string, Promise<{ name: string; description: string; config: Record<string, any> }>>();
// Cache last extracted UI config per assistant so multiple hook instances can sync state
const lastExtractedByAssistantId = new Map<
  string,
  {
    configurations: ConfigurableFieldUIMetadata[];
    toolConfigurations: ConfigurableFieldMCPMetadata[];
    ragConfigurations: ConfigurableFieldRAGMetadata[];
    agentsConfigurations: ConfigurableFieldAgentsMetadata[];
    supportedConfigs: string[];
    inputSchema: GraphSchema["input_schema"] | null;
    inputMode: InputMode;
  }
>();

export function useAgentConfig() {
  const { getAgentConfigSchema, getAgent } = useAgents();
  const [chatWithCollectionId, setChatWithCollectionId] = useQueryState(
    "chatWithCollectionId",
  );

  const [configurations, setConfigurations] = useState<
    ConfigurableFieldUIMetadata[]
  >([]);
  const [toolConfigurations, setToolConfigurations] = useState<
    ConfigurableFieldMCPMetadata[]
  >([]);
  const [ragConfigurations, setRagConfigurations] = useState<
    ConfigurableFieldRAGMetadata[]
  >([]);
  const [agentsConfigurations, setAgentsConfigurations] = useState<
    ConfigurableFieldAgentsMetadata[]
  >([]);

  const [supportedConfigs, setSupportedConfigs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  
  // New state for input schema and mode detection
  const [inputSchema, setInputSchema] = useState<GraphSchema["input_schema"] | null>(null);
  const [inputMode, setInputMode] = useState<InputMode>('loading');

  const clearState = useCallback(() => {
    setConfigurations([]);
    setToolConfigurations([]);
    setRagConfigurations([]);
    setAgentsConfigurations([]);
    // Do not modify loading here to avoid transient empty UI while not loading
    setInputSchema(null);
    setInputMode('loading');
  }, []);



  const getSchemaAndUpdateConfig = useCallback(
    async (
      agent: Agent,
    ): Promise<{
      name: string;
      description: string;
      config: Record<string, any>;
    }> => {
      // Deduplicate concurrent loads for the same assistant
      const existing = inflightLoads.get(agent.assistant_id);
      if (existing) {
        // Bring this hook instance along for the ride: show loading and sync from cache when done
        setLoading(true);
        try {
          const res = await existing;
          const cached = lastExtractedByAssistantId.get(agent.assistant_id);
          if (cached) {
            setConfigurations(cached.configurations);
            setToolConfigurations(cached.toolConfigurations);
            setRagConfigurations(cached.ragConfigurations);
            setAgentsConfigurations(cached.agentsConfigurations);
            setSupportedConfigs(cached.supportedConfigs);
            setInputSchema(cached.inputSchema);
            setInputMode(cached.inputMode);
          }
          return res;
        } finally {
          setLoading(false);
        }
      }

      // Wrap the loader to register in-flight and ensure cleanup
      const loader = (async () => {
        setLoading(true);
        clearState();
        try {
        // debug logs removed

        // First, get the agent's current configuration from the backend
        let fullAgentDetails = null;
        
        try {
          const agentResult = await getAgent(agent.assistant_id, agent.deploymentId);
          if (agentResult.ok) {
            fullAgentDetails = agentResult.data;
          } else {
            console.warn(`❌ [useAgentConfig] Failed to fetch agent details:`, agentResult.errorMessage);
          }
        } catch (error) {
          console.warn(`❌ [useAgentConfig] Exception fetching full agent details for ${agent.assistant_id}:`, error);
        }

        const schema = await getAgentConfigSchema(
          agent.assistant_id,
          agent.deploymentId,
        );
        // debug logs removed
        
        if (!schema) {
          // Check if this might be a recently created agent
          const createdAt = agent.created_at ? new Date(agent.created_at) : null;
          const isRecent = createdAt && (Date.now() - createdAt.getTime()) < 5 * 60 * 1000; // 5 minutes
          
          // Recently created agents might not have schema propagated yet; only warn when not recent
          if (!isRecent) {
            console.warn(`Failed to fetch schema for agent ${agent.assistant_id} (${agent.name}) - falling back to chat mode`);
          }
          
          setInputMode('chat'); // Default to chat mode if no schema
          return {
            name: agent.name,
            description:
              (agent.metadata?.description as string | undefined) ?? "",
            config: {},
          };
        }
        
        // Process input schema for mode detection
        // Check if we have a traditional input_schema or need to use state_schema
        let effectiveInputSchema = schema.input_schema;
        
        // If input_schema is null but state_schema has user input fields, use state_schema
        if (!effectiveInputSchema && schema.state_schema?.properties) {
          const stateProps = schema.state_schema.properties;
          // Look for common user input fields (topic, query, etc.) but exclude system fields
          const userInputFields = Object.keys(stateProps).filter(key => 
            !key.includes('message') && 
            !key.includes('progress') && 
            !key.includes('section') && 
            !key.includes('citation') && 
            !key.includes('completed') &&
            !key.includes('final') &&
            !key.includes('search_') &&
            !key.includes('source_') &&
            !key.includes('report_') &&
            ['topic', 'query', 'input', 'question'].some(field => key.toLowerCase().includes(field))
          );
          
          if (userInputFields.length > 0) {
            // Create a synthetic input schema from relevant state fields
            effectiveInputSchema = {
              type: 'object',
              properties: Object.fromEntries(
                userInputFields.map(key => [key, stateProps[key]])
              ),
              required: [] // For now, don't mark any fields as required from state schema
            };
          }
        }
        
        setInputSchema(effectiveInputSchema);
    
        
        if (effectiveInputSchema?.properties?.messages) {
          setInputMode('chat');
        } else if (effectiveInputSchema) {
          setInputMode('form');
        } else {
          setInputMode('chat'); // Fallback to chat if no schema
        }
        
        // Create an agent object with the full config for proper extraction
        const agentWithFullConfig = {
          ...agent,
          config: fullAgentDetails?.config || agent.config || {},
        };

        // Extract config fields using the agent with full config
        const { configFields, toolConfig, ragConfig, agentsConfig } =
          extractConfigurationsFromAgent({
            agent: agentWithFullConfig,
            schema: schema.config_schema,
          });

        const agentId = agent.assistant_id;

        setConfigurations(configFields);
        setToolConfigurations(toolConfig);

        // Set config values using the extracted configurations (which already have the saved values merged)
        const { setDefaultConfig } = useConfigStore.getState();
        
        setDefaultConfig(agentId, configFields);

        const supportedConfigs: string[] = [];

        if (toolConfig.length) {
          setDefaultConfig(`${agentId}:selected-tools`, toolConfig);
          setToolConfigurations(toolConfig);
          supportedConfigs.push("tools");
        }
        if (ragConfig.length) {
          if (chatWithCollectionId) {
            ragConfig[0].default = {
              ...ragConfig[0].default,
              collections: [chatWithCollectionId],
            };
            // Clear from query params so it's not set again.
            setChatWithCollectionId(null);
          }
          setDefaultConfig(`${agentId}:rag`, ragConfig);
          setRagConfigurations(ragConfig);
          supportedConfigs.push("rag");
        }
        if (agentsConfig.length) {
          // Stash UI metadata (e.g., mode) for components that need it
          setDefaultConfig(`${agentId}:agents`, agentsConfig);
          // Do NOT overwrite the base config; update only the __ui_meta key
          try {
            const { updateConfig } = useConfigStore.getState();
            updateConfig(agentId, "__ui_meta", {
              [agentsConfig[0].label]: { mode: agentsConfig[0].mode },
            });
          } catch (_e) {
            void 0; // ignore UI meta update errors
          }
          setAgentsConfigurations(agentsConfig);
          supportedConfigs.push("supervisor");
          // Pre-populate saved sub-agents into the config store for builder mode
          const savedSubAgents = (agentWithFullConfig.config as any)?.[agentsConfig[0].label] ?? [];
          try {
            const { updateConfig } = useConfigStore.getState();
            updateConfig(agentId, agentsConfig[0].label, Array.isArray(savedSubAgents) ? savedSubAgents : []);
          } catch (_e) {
            void 0; // ignore sub-agent pre-populate errors
          }
        }
        setSupportedConfigs(supportedConfigs);
        // debug logs removed

        // Update cache for other hook instances
        lastExtractedByAssistantId.set(agent.assistant_id, {
          configurations: configFields,
          toolConfigurations: toolConfig,
          ragConfigurations: ragConfig,
          agentsConfigurations: agentsConfig,
          supportedConfigs,
          inputSchema: effectiveInputSchema ?? null,
          inputMode: effectiveInputSchema?.properties?.messages ? 'chat' : (effectiveInputSchema ? 'form' : 'chat'),
        });

        const configurableDefaults = getConfigurableDefaults(
          configFields,
          toolConfig,
          ragConfig,
          agentsConfig,
        );

        // Prefer saved sub-agents from backend config when available
        const savedSubAgents = (agentWithFullConfig.config as any)?.[agentsConfig[0]?.label ?? "sub_agents"];
        if (Array.isArray(savedSubAgents)) {
          configurableDefaults[agentsConfig[0]?.label ?? "sub_agents"] = savedSubAgents;
        } else {
          // Fallback to store if present
          const { configsByAgentId } = useConfigStore.getState();
          const subAgentsFromStore = configsByAgentId[agent.assistant_id]?.[agentsConfig[0]?.label ?? "sub_agents"];
          if (Array.isArray(subAgentsFromStore)) {
            configurableDefaults[agentsConfig[0]?.label ?? "sub_agents"] = subAgentsFromStore;
          }
        }
        
        const result = {
          name: agent.name,
          description:
            (agent.metadata?.description as string | undefined) ?? "",
          config: configurableDefaults,
        };
        // debug logs removed
        
        return result;
      } finally {
        setLoading(false);
        // debug logs removed
      }
      })();

      inflightLoads.set(agent.assistant_id, loader);
      try {
        const res = await loader;
        return res;
      } finally {
        inflightLoads.delete(agent.assistant_id);
      }
    },
    [clearState, getAgentConfigSchema, getAgent, chatWithCollectionId, setChatWithCollectionId],
  );

  return {
    clearState,
    getSchemaAndUpdateConfig,

    configurations,
    toolConfigurations,
    ragConfigurations,
    agentsConfigurations,
    supportedConfigs,

    loading,
    
    // New input schema properties
    inputSchema,
    inputMode,
  };
}
