import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useAgents } from "@/hooks/use-agents";
import { Bot, LoaderCircle, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { notify } from "@/utils/toast";
import { agentMessages } from "@/utils/toast-messages";
import { useAgentsContext } from "@/providers/Agents";
import { AgentFieldsForm, AgentFieldsFormLoading } from "./agent-form";
import { Deployment } from "@/types/deployment";
import { Agent } from "@/types/agent";
import { getDeployments } from "@/lib/environment/deployments";
import { GraphSelect } from "./graph-select";
import { useAgentConfig } from "@/hooks/use-agent-config";
import { FormProvider, useForm } from "react-hook-form";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { useAuthContext } from "@/providers/Auth";

interface CreateAgentDialogProps {
  agentId?: string;
  deploymentId?: string;
  graphId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function CreateAgentFormContent(props: {
  selectedGraph: Agent;
  selectedDeployment: Deployment;
  onClose: () => void;
}) {
  const form = useForm<{
    name: string;
    description: string;
    config: Record<string, any>;
  }>({
    defaultValues: async () => {
      const values = await getSchemaAndUpdateConfig(props.selectedGraph);
      return {
        name: "",
        description: (props.selectedGraph as any).description ?? "",
        config: values.config,
      };
    },
  });

  const { createAgent } = useAgents();
  const { refreshAgents, invalidateAssistantListCache, invalidateAllAssistantCaches, addAgentToList } = useAgentsContext();
  const { session } = useAuthContext();
  const {
    getSchemaAndUpdateConfig,
    loading,
    configurations,
    toolConfigurations,
    ragConfigurations,
    agentsConfigurations,
  } = useAgentConfig();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (data: {
    name: string;
    description: string;
    config: Record<string, any>;
  }) => {
    const { name, description, config } = data;
    if (!name || !description) {
      const message = agentMessages.validation.nameDescriptionRequired();
      notify.warning(message.title, { 
        description: message.description,
        key: message.key 
      });
      return;
    }

    setSubmitting(true);
    const result = await createAgent(
      props.selectedDeployment.id,
      props.selectedGraph.graph_id,
      {
        name,
        description,
        config,
      },
    );
    setSubmitting(false);

    if (!result.ok) {
      console.error("❌ Agent creation failed:", result.errorMessage);
      const message = agentMessages.create.error();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
      return;
    }

    const newAgent = result.data!;

    const optimisticAgent = {
      ...newAgent,
      deploymentId: props.selectedDeployment.id,
      permission_level: "owner" as const,
      owner_id: typeof newAgent.metadata?.owner === 'string' ? newAgent.metadata.owner : "",
      owner_display_name: "You",
    };
    
    // Immediately add the agent to the UI for instant feedback
    addAgentToList(optimisticAgent);
    

    // Close the dialog immediately for better UX
    props.onClose();

    // Show success toast immediately
    if (newAgent.schemas_warming) {
      const message = agentMessages.create.successWithWarming(newAgent.name);
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });
    } else {
      const message = agentMessages.create.success(newAgent.name);
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });
    }

    // Show registration warning if needed
    if (newAgent.registrationWarning) {
      const message = agentMessages.create.registrationWarning();
      notify.warning(message.title, {
        description: message.description,
      });
    }

    // Background validation to ensure consistency (non-blocking)
    // Wait for backend mirroring to complete, then validate
    setTimeout(async () => {
      try {
        
        // Step 1: Force sync by triggering a full user-scoped refresh
        // Since admin sync can't see user agents, we trigger a user-scoped sync via refresh
        
        // Wait a bit for LangConnect registration to complete
        await new Promise(resolve => setTimeout(resolve, 500));
        
        try {
          // Trigger a fresh discovery call which will force the backend to sync user data
          const discoveryResponse = await fetch(`/api/langconnect/user/accessible-graphs?deploymentId=${newAgent.deploymentId}`, {
            headers: {
              Authorization: `Bearer ${session?.accessToken}`,
              "Content-Type": "application/json",
            },
          });
          
          if (discoveryResponse.ok) {
            // Discovery sync successful
          } else {
            console.warn("⚠️ User-scoped discovery sync failed:", discoveryResponse.status);
          }
        } catch (syncError) {
          console.warn("⚠️ User-scoped sync failed:", syncError);
        }
        
        // Step 2: Wait a bit more, then validate the UI is consistent
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        invalidateAssistantListCache();
        invalidateAllAssistantCaches();
        
        // Silent refresh to check if our optimistic update was correct
        await refreshAgents(true);  
      } catch (e) {
        console.error("⚠️ Background validation failed (non-critical):", e);
        // Don't show error to user since optimistic update should be working
      }
    }, 3000); // Wait 3 seconds for backend mirroring to complete
  };

  return (
    <form onSubmit={form.handleSubmit(handleSubmit)}>
      {loading ? (
        <AgentFieldsFormLoading />
      ) : (
        <FormProvider {...form}>
          <AgentFieldsForm
            agentId={props.selectedGraph.assistant_id}
            configurations={configurations}
            toolConfigurations={toolConfigurations}
            ragConfigurations={ragConfigurations}
            agentsConfigurations={agentsConfigurations}
          />
        </FormProvider>
      )}
      <AlertDialogFooter>
        <Button
          onClick={(e) => {
            e.preventDefault();
            props.onClose();
          }}
          variant="outline"
          disabled={loading || submitting}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          className="flex w-full items-center justify-center gap-1"
          disabled={loading || submitting}
        >
          {submitting ? <LoaderCircle className="animate-spin" /> : <Bot />}
          <span>{submitting ? "Creating..." : "Create Agent"}</span>
        </Button>
      </AlertDialogFooter>
    </form>
  );
}

export function CreateAgentDialog({
  agentId,
  deploymentId,
  graphId,
  open,
  onOpenChange,
}: CreateAgentDialogProps) {
  const deployments = getDeployments();
  const { agents } = useAgentsContext();

  const [selectedDeployment, setSelectedDeployment] = useState<
    Deployment | undefined
  >();
  const [selectedGraph, setSelectedGraph] = useState<Agent | undefined>();

  useEffect(() => {
    if (selectedDeployment || selectedGraph) return;
    if (agentId && deploymentId && graphId) {
      // Find the deployment & default agent, then set them
      const deployment = deployments.find((d) => d.id === deploymentId);
      const defaultAgent = agents.find(
        (a) => a.assistant_id === agentId && a.deploymentId === deploymentId,
      );
      if (!deployment || !defaultAgent) {
        const message = agentMessages.fetch.error();
        notify.error(message.title, {
          description: message.description,
          key: message.key,
        });
        return;
      }

      setSelectedDeployment(deployment);
      setSelectedGraph(defaultAgent);
    }
  }, [
    agentId,
    deploymentId,
    graphId,
    agents,
    deployments,
    selectedDeployment,
    selectedGraph,
  ]);

  const [openCounter, setOpenCounter] = useState(0);

  const lastOpen = useRef(open);
  useLayoutEffect(() => {
    if (lastOpen.current !== open && open) {
      setOpenCounter((c) => c + 1);
    }
    lastOpen.current = open;
  }, [open, setOpenCounter]);

  return (
    <AlertDialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <AlertDialogContent className={cn("h-auto max-h-[90vh] sm:max-w-lg md:max-w-2xl lg:max-w-3xl", ...getScrollbarClasses('y'))}>
        <AlertDialogHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1.5">
              <AlertDialogTitle>Create Agent</AlertDialogTitle>
              <AlertDialogDescription>
                Create a new agent using the &apos;
                <span className="font-medium">{selectedGraph?.graph_id}</span>
                &apos; template.
              </AlertDialogDescription>
            </div>
            <AlertDialogCancel size="icon">
              <X className="size-4" />
            </AlertDialogCancel>
          </div>
        </AlertDialogHeader>

        {!agentId && !graphId && !deploymentId && (
          <div className="flex flex-col items-start justify-start gap-2">
            <p>Please select a template to create an agent for.</p>
            <GraphSelect
              className="w-full"
              agents={agents}
              selectedGraph={selectedGraph}
              setSelectedGraph={setSelectedGraph}
              selectedDeployment={selectedDeployment}
              setSelectedDeployment={setSelectedDeployment}
            />
          </div>
        )}

        {selectedGraph && selectedDeployment ? (
          <CreateAgentFormContent
            key={openCounter}
            selectedGraph={selectedGraph}
            selectedDeployment={selectedDeployment}
            onClose={() => onOpenChange(false)}
          />
        ) : null}
      </AlertDialogContent>
    </AlertDialog>
  );
}
