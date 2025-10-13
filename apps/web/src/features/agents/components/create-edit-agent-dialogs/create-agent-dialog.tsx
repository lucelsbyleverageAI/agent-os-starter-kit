import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useAgents } from "@/hooks/use-agents";
import { ArrowLeft, Bot, LoaderCircle, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { notify } from "@/utils/toast";
import { agentMessages } from "@/utils/toast-messages";
import { useAgentsContext } from "@/providers/Agents";
import { AgentFieldsForm, AgentFieldsFormLoading } from "./agent-form";
import { Deployment } from "@/types/deployment";
import { getDeployments } from "@/lib/environment/deployments";
import { GraphTemplateSelector } from "./graph-template-selector";
import { useAgentConfig } from "@/hooks/use-agent-config";
import { FormProvider, useForm } from "react-hook-form";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { useAuthContext } from "@/providers/Auth";
import { logger } from "@/lib/logger";

interface CreateAgentDialogProps {
  agentId?: string;
  deploymentId?: string;
  graphId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function CreateAgentFormContent(props: {
  graphId: string;
  graphName: string;
  graphDescription: string;
  selectedDeployment: Deployment;
  onClose: () => void;
  onSuccess: () => void;
  onBack: () => void;
  setFormIsDirty: (isDirty: boolean) => void;
}) {
  const form = useForm<{
    name: string;
    description: string;
    tags: string[];
    config: Record<string, any>;
  }>({
    defaultValues: async () => {
      const values = await getGraphSchemaAndUpdateConfig(
        props.graphId,
        props.graphName,
        props.graphDescription
      );
      return {
        name: "",
        description: values.description ?? "",
        tags: [],
        config: values.config,
      };
    },
  });

  // Track form dirty state
  useEffect(() => {
    props.setFormIsDirty(form.formState.isDirty);
  }, [form.formState.isDirty, props]);

  const { createAgent } = useAgents();
  const { refreshAgents, invalidateAssistantListCache, invalidateAllAssistantCaches, addAgentToList } = useAgentsContext();
  const { session } = useAuthContext();
  const {
    getGraphSchemaAndUpdateConfig,
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
    tags: string[];
    config: Record<string, any>;
  }) => {
    const { name, description, tags, config } = data;
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
      props.graphId,
      {
        name,
        description,
        config,
        tags: tags || [],
      },
    );
    setSubmitting(false);

    if (!result.ok) {
      logger.error("Agent creation failed:", result.errorMessage);
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


    // Close the dialog immediately for better UX (bypass confirmation)
    props.onSuccess();

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

    // Note: We no longer show registration warnings to users as they can be confusing.
    // The agent is fully functional even if registration temporarily fails, and the
    // background sync process will handle any permission system updates automatically.

    // Background validation to ensure consistency (non-blocking)
    // Wait for backend mirroring to complete, then validate
    setTimeout(async () => {
      try {
        // Wait for backend registration and mirroring to complete
        await new Promise(resolve => setTimeout(resolve, 1500));

        // Invalidate caches to force fresh data on next request
        invalidateAssistantListCache();
        invalidateAllAssistantCaches();

        // Silent refresh to validate that our optimistic update was correct
        await refreshAgents(true);
      } catch (e) {
        logger.error("Background validation failed (non-critical):", e);
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
              agentId={`graph_template:${props.graphId}`}
              configurations={configurations}
              toolConfigurations={toolConfigurations}
              ragConfigurations={ragConfigurations}
              agentsConfigurations={agentsConfigurations}
            />
          </FormProvider>
      )}
      <AlertDialogFooter>
        <div className="flex w-full items-center justify-between gap-2">
          <Button
            onClick={(e) => {
              e.preventDefault();
              props.onBack();
            }}
            variant="ghost"
            size="sm"
            disabled={loading || submitting}
            className="gap-1"
          >
            <ArrowLeft className="size-4" />
            <span>Back</span>
          </Button>
          <div className="flex gap-2">
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
              className="flex items-center justify-center gap-1"
              disabled={loading || submitting}
            >
              {submitting ? <LoaderCircle className="animate-spin" /> : <Bot />}
              <span>{submitting ? "Creating..." : "Create Agent"}</span>
            </Button>
          </div>
        </div>
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
  const { agents, discoveryData } = useAgentsContext();

  const [selectedDeployment, setSelectedDeployment] = useState<
    Deployment | undefined
  >();
  const [selectedGraphId, setSelectedGraphId] = useState<string | undefined>();
  const [selectedGraphName, setSelectedGraphName] = useState<string>("");
  const [selectedGraphDescription, setSelectedGraphDescription] = useState<string>("");
  const [showConfirmClose, setShowConfirmClose] = useState(false);
  const [formIsDirty, setFormIsDirty] = useState(false);

  useEffect(() => {
    if (selectedDeployment || selectedGraphId) return;
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
      setSelectedGraphId(defaultAgent.graph_id);
      setSelectedGraphName(defaultAgent.name);
      setSelectedGraphDescription(defaultAgent.description || "");
    }
  }, [
    agentId,
    deploymentId,
    graphId,
    agents,
    deployments,
    selectedDeployment,
    selectedGraphId,
  ]);

  // Handle graph selection from the card selector
  const handleGraphSelect = (graphId: string) => {
    setSelectedGraphId(graphId);

    // Find the deployment (use first/default for now)
    const deployment = deployments.find((d) => d.isDefault) || deployments[0];
    setSelectedDeployment(deployment);

    // Find the graph info from discoveryData
    const graphInfo = discoveryData?.valid_graphs.find((g) => g.graph_id === graphId);

    if (!graphInfo) {
      logger.error(`No graph info found for ${graphId}`);
      const message = agentMessages.fetch.error();
      notify.error(message.title, {
        description: "Could not load configuration schema for this template",
        key: message.key,
      });
      return;
    }

    // Set graph metadata
    setSelectedGraphName(graphInfo.name || graphId);
    setSelectedGraphDescription(graphInfo.description || "");
  };

  // Reset state when modal closes
  useEffect(() => {
    if (!open) {
      // Reset all state
      setSelectedDeployment(undefined);
      setSelectedGraphId(undefined);
      setSelectedGraphName("");
      setSelectedGraphDescription("");
      setFormIsDirty(false);
      setShowConfirmClose(false);
    }
  }, [open]);

  // Handle back navigation from config to template selection
  const handleBack = () => {
    setSelectedGraphId(undefined);
    setSelectedGraphName("");
    setSelectedGraphDescription("");
    setSelectedDeployment(undefined);
    setFormIsDirty(false);
  };

  // Handle close with confirmation if form is dirty
  const handleClose = () => {
    if (formIsDirty && selectedGraphId) {
      setShowConfirmClose(true);
    } else {
      onOpenChange(false);
    }
  };

  const confirmClose = () => {
    setShowConfirmClose(false);
    onOpenChange(false);
  };

  const cancelClose = () => {
    setShowConfirmClose(false);
  };

  const [openCounter, setOpenCounter] = useState(0);

  const lastOpen = useRef(open);
  useLayoutEffect(() => {
    if (lastOpen.current !== open && open) {
      setOpenCounter((c) => c + 1);
    }
    lastOpen.current = open;
  }, [open, setOpenCounter]);

  return (
    <>
      <AlertDialog
        open={open}
        onOpenChange={(newOpen) => {
          if (!newOpen) {
            handleClose();
          } else {
            onOpenChange(newOpen);
          }
        }}
      >
        <AlertDialogContent className={cn("h-auto max-h-[90vh] sm:max-w-2xl md:max-w-4xl lg:max-w-5xl", ...getScrollbarClasses('y'))}>
          <AlertDialogHeader>
            <div className="flex items-start justify-between gap-4">
              <div className="flex flex-col gap-1.5">
                <AlertDialogTitle>
                  {!selectedGraphId || (!agentId && !graphId && !deploymentId)
                    ? "Create Agent"
                    : `Create ${selectedGraphId ? selectedGraphId.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ") : "Agent"}`}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  {!selectedGraphId || (!agentId && !graphId && !deploymentId)
                    ? "Select a template to create your new agent"
                    : `Configure your new agent using the ${selectedGraphId} template`}
                </AlertDialogDescription>
              </div>
              <AlertDialogCancel size="icon" onClick={(e) => {
                e.preventDefault();
                handleClose();
              }}>
                <X className="size-4" />
              </AlertDialogCancel>
            </div>
          </AlertDialogHeader>

          {/* Show graph selector if no graph is selected */}
          {!agentId && !graphId && !deploymentId && !selectedGraphId && (
            <GraphTemplateSelector
              graphs={discoveryData?.valid_graphs || []}
              selectedGraphId={selectedGraphId}
              onSelectGraph={handleGraphSelect}
            />
          )}

          {/* Show form once graph is selected */}
          {selectedGraphId && selectedDeployment ? (
            <CreateAgentFormContent
              key={openCounter}
              graphId={selectedGraphId}
              graphName={selectedGraphName}
              graphDescription={selectedGraphDescription}
              selectedDeployment={selectedDeployment}
              onClose={handleClose}
              onSuccess={() => onOpenChange(false)}
              onBack={handleBack}
              setFormIsDirty={setFormIsDirty}
            />
          ) : null}
        </AlertDialogContent>
      </AlertDialog>

      {/* Confirmation dialog for unsaved changes */}
      <AlertDialog open={showConfirmClose} onOpenChange={setShowConfirmClose}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard changes?</AlertDialogTitle>
            <AlertDialogDescription>
              You have unsaved changes. Are you sure you want to close? Your changes will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={cancelClose}>
              Continue Editing
            </AlertDialogCancel>
            <AlertDialogAction onClick={confirmClose}>
              Discard Changes
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
