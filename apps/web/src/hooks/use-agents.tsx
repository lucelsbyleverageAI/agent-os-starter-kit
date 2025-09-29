import { createClient } from "@/lib/client";
import { Agent, AgentSchemaResponse } from "@/types/agent";
import { useAuthContext } from "@/providers/Auth";
import { useCallback } from "react";
import { isSystemCreatedDefaultAssistant } from "@/lib/agent-utils";

// Result types for consistent error handling
interface SuccessResult<T = void> {
  ok: true;
  data?: T;
}

interface ErrorResult {
  ok: false;
  errorCode: string;
  errorMessage: string;
}

type Result<T = void> = SuccessResult<T> | ErrorResult;

export function useAgents() {
  const { session } = useAuthContext();

  const getAgent = useCallback(
    async (
      agentId: string,
      deploymentId: string,
    ): Promise<Result<Agent>> => {
      
      if (!session?.accessToken) {
        console.warn(`❌ [getAgent] No access token available`);
        return {
          ok: false,
          errorCode: "NO_ACCESS_TOKEN",
          errorMessage: "No access token found",
        };
      }
      
      try {
        const url = `/api/langconnect/agents/mirror/assistants/${agentId}?ts=${Date.now()}`;

        const response = await fetch(url, {
          cache: 'no-store',
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
          },
        });


        if (!response.ok) {
          const errorText = await response.text();
          console.warn(`❌ [getAgent] Fetch failed:`, { status: response.status, errorText });
          return {
            ok: false,
            errorCode: "FETCH_FAILED",
            errorMessage: `Mirror assistant fetch failed: ${response.status} ${errorText}`,
          };
        }

        const assistant = await response.json();
        
        // Parse JSONB fields if they're strings (from database)
        const parseJsonField = (field: any, fieldName: string) => {
          if (typeof field === 'string') {
            try {
              const parsed = JSON.parse(field);
              return parsed;
            } catch (error) {
              console.warn(`⚠️ [getAgent] Failed to parse ${fieldName} string:`, error);
              return {};
            }
          }
          return field || {};
        };
        
        assistant.config = parseJsonField(assistant.config, 'config');
        assistant.metadata = parseJsonField(assistant.metadata, 'metadata');
        assistant.context = parseJsonField(assistant.context, 'context');
        


        if (isSystemCreatedDefaultAssistant(assistant)) {
          return {
            ok: false,
            errorCode: "SYSTEM_ASSISTANT",
            errorMessage: "System-created default assistant",
          };
        }
        
        return {
          ok: true,
          data: { ...assistant, deploymentId } as Agent,
        };
      } catch (error) {
        return {
          ok: false,
          errorCode: "UNKNOWN_ERROR",
          errorMessage: error instanceof Error ? error.message : "Failed to get agent",
        };
      }
    },
    [session?.accessToken],
  );

  const getAgentConfigSchema = useCallback(
    async (agentId: string, _deploymentId: string | null): Promise<AgentSchemaResponse | undefined> => {
      if (!session?.accessToken) return undefined;

      const parseMaybeJson = (v: unknown) => {
        if (v == null) return null as any;
        if (typeof v === 'string') {
          try { return JSON.parse(v); } catch { return null as any; }
        }
        return v as any;
      };

      try {
        const response = await fetch(`/api/langconnect/agents/mirror/assistants/${agentId}/schemas?ts=${Date.now()}` , {
          cache: 'no-store',
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
          },
        });

        if (response.status === 202) {
          // Schemas warming – let UI show default chat and try later
          return undefined;
        }
        if (!response.ok) {
          if (response.status === 403 || response.status === 404) return undefined;
          return undefined;
        }

        const raw = await response.json();
        const normalised: AgentSchemaResponse = {
          input_schema: parseMaybeJson(raw.input_schema),
          config_schema: parseMaybeJson(raw.config_schema),
          state_schema: parseMaybeJson(raw.state_schema),
        } as AgentSchemaResponse;
        return normalised;
      } catch {
        return undefined;
      }
    },
    [session?.accessToken],
  );

  const createAgent = useCallback(
    async (
      deploymentId: string,
      graphId: string,
      formData: {
        name: string;
        description: string;
        config: Record<string, any>;
      },
    ): Promise<Result<Agent & { schemas_warming?: boolean; registrationWarning?: boolean }>> => {
      if (!session?.accessToken) {
        return {
          ok: false,
          errorCode: "NO_ACCESS_TOKEN",
          errorMessage: "No access token found",
        };
      }

      try {
        // Stage 1: Create assistant in LangGraph (mutations remain via SDK)
        const client = createClient(deploymentId, session.accessToken);
        const assistant = await client.assistants.create({
          graphId: graphId,
          name: formData.name,
          config: formData.config,
          // Prefer top-level description; keep owner in metadata if needed by LG
          description: formData.description,
          metadata: {
            owner: session.user?.id,
          },
        });

        // Stage 2: Register assistant in LangConnect permission system
        let schemas_warming = false;
        let registrationWarning = false;
        
        try {
          const registrationResponse = await fetch("/api/langconnect/agents/assistants", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${session.accessToken}`,
            },
            body: JSON.stringify({
              assistant_id: assistant.assistant_id,
              name: formData.name,
              description: formData.description,
              config: formData.config, // Include config in registration
              reason: "Assistant created via UI",
            }),
          });

          if (registrationResponse.ok) {
            const registrationData = await registrationResponse.json();
            schemas_warming = registrationData.schemas_warming || false;
          } else {
            registrationWarning = true;
          }
        } catch (_registrationError) {
          registrationWarning = true;
        }

        return {
          ok: true,
          data: {
            ...assistant,
            deploymentId,
            schemas_warming,
            registrationWarning,
          },
        };
      } catch (error) {
        return {
          ok: false,
          errorCode: "CREATE_FAILED",
          errorMessage: error instanceof Error ? error.message : "Failed to create agent",
        };
      }
    },
    [session?.accessToken, session?.user?.id],
  );

  const updateAgent = useCallback(
    async (
      agentId: string,
      deploymentId: string,
      formData: {
        name?: string;
        description?: string;
        config?: Record<string, any>;
      },
    ): Promise<Result<Agent>> => {
      if (!session?.accessToken) {
        return {
          ok: false,
          errorCode: "NO_ACCESS_TOKEN",
          errorMessage: "No access token found",
        };
      }

      try {
        // Stage 1: Update assistant in LangGraph (mutations remain via SDK)
        const client = createClient(deploymentId, session.accessToken);
        const updatePayload: any = {};
        if (formData.name) updatePayload.name = formData.name;
        if (formData.config) updatePayload.config = formData.config;
        if (formData.description !== undefined) {
          // Prefer top-level description when supported
          (updatePayload as any).description = formData.description;
        }
        const updatedAssistant = await client.assistants.update(agentId, updatePayload);

        // Stage 2: Sync changes to LangConnect backend (this will update the mirror)
        try {
          const syncPayload: any = {};
          if (formData.name) syncPayload.name = formData.name;
          if (formData.description !== undefined) syncPayload.description = formData.description;
          if (formData.config) syncPayload.config = formData.config;

          const syncResponse = await fetch(`/api/langconnect/agents/assistants/${agentId}`, {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${session.accessToken}`,
            },
            body: JSON.stringify({
              ...syncPayload,
              reason: "Assistant updated via UI",
            }),
          });

          if (!syncResponse.ok) {
            console.warn(`Failed to sync assistant ${agentId} to LangConnect: ${syncResponse.status}`);
          }
        } catch (syncError) {
          console.warn(`Failed to sync assistant ${agentId} to LangConnect:`, syncError);
          // Don't fail the update if sync fails - LangGraph update succeeded
        }

        return {
          ok: true,
          data: {
            ...updatedAssistant,
            deploymentId,
          },
        };
      } catch (error) {
        return {
          ok: false,
          errorCode: "UPDATE_FAILED",
          errorMessage: error instanceof Error ? error.message : "Failed to update agent",
        };
      }
    },
    [session?.accessToken, session?.user?.id],
  );

  const deleteAgent = useCallback(
    async (deploymentId: string, agentId: string): Promise<Result> => {
      if (!session?.accessToken) {
        return {
          ok: false,
          errorCode: "NO_ACCESS_TOKEN",
          errorMessage: "No access token found",
        };
      }

      try {
        // Use LangConnect permission-aware delete endpoint
        const deleteResponse = await fetch(`/api/langconnect/agents/assistants/${agentId}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
        });

        if (!deleteResponse.ok) {
          return {
            ok: false,
            errorCode: "DELETE_FAILED",
            errorMessage: "Failed to delete agent",
          };
        }

        return { ok: true };
      } catch (error) {
        return {
          ok: false,
          errorCode: "DELETE_ERROR",
          errorMessage: error instanceof Error ? error.message : "Failed to delete agent",
        };
      }
    },
    [session?.accessToken],
  );

  const revokeMyAccess = useCallback(
    async (assistantId: string): Promise<Result> => {
      if (!session?.accessToken) {
        return {
          ok: false,
          errorCode: "NO_ACCESS_TOKEN",
          errorMessage: "No access token found",
        };
      }

      if (!session?.user?.id) {
        return {
          ok: false,
          errorCode: "NO_USER_ID",
          errorMessage: "User ID not found",
        };
      }

      try {
        const revokeResponse = await fetch(`/api/langconnect/agents/assistants/${assistantId}/permissions/${session.user.id}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
        });

        if (!revokeResponse.ok) {
          return {
            ok: false,
            errorCode: "REVOKE_FAILED",
            errorMessage: "Failed to revoke access",
          };
        }

        return { ok: true };
      } catch (error) {
        return {
          ok: false,
          errorCode: "REVOKE_ERROR",
          errorMessage: error instanceof Error ? error.message : "Failed to revoke access",
        };
      }
    },
    [session?.accessToken, session?.user?.id],
  );

  return {
    getAgent,
    getAgentConfigSchema,
    createAgent,
    updateAgent,
    deleteAgent,
    revokeMyAccess,
  };
}
