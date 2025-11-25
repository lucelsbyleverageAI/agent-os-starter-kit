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
import { useAgentConfig, clearAgentConfigCache } from "@/hooks/use-agent-config";
import { Bot, LoaderCircle, Trash, X } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";
import { notify } from "@/utils/toast";
import { agentMessages } from "@/utils/toast-messages";
import { useAgentsContext } from "@/providers/Agents";
import { AgentFieldsForm, AgentFieldsFormLoading } from "./agent-form";
import { Agent } from "@/types/agent";
import { FormProvider, useForm } from "react-hook-form";
import { canUserDeleteAssistant, canUserRevokeOwnAccess } from "@/lib/agent-utils";
import { Badge } from "@/components/ui/badge";
import { Crown, Edit, Shield, UserMinus } from "lucide-react";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { logger } from "@/lib/logger";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface EditAgentDialogProps {
  agent: Agent;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function EditAgentDialogContent({
  agent,
  onClose,
}: {
  agent: Agent;
  onClose: () => void;
}) {
  const { updateAgent, deleteAgent, revokeMyAccess, getAgent } = useAgents();
  const { refreshAgents, invalidateAssistantListCache } = useAgentsContext();
  const {
    getSchemaAndUpdateConfig,

    loading,
    configurations,
    toolConfigurations,
    ragConfigurations,
    agentsConfigurations,
    skillsConfigurations,
  } = useAgentConfig();
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [revokeSubmitting, setRevokeSubmitting] = useState(false);
  const [deleteConfirmDialogOpen, setDeleteConfirmDialogOpen] = useState(false);
  const [commitMessageDialogOpen, setCommitMessageDialogOpen] = useState(false);
  const [commitMessage, setCommitMessage] = useState("");
  const [pendingFormData, setPendingFormData] = useState<{
    name: string;
    description: string;
    tags: string[];
    config: Record<string, any>;
  } | null>(null);

  // Check user permissions
  const canDelete = canUserDeleteAssistant(agent);
  const canRevokeOwnAccess = canUserRevokeOwnAccess(agent);
  const permissionLevel = agent.permission_level;

  const form = useForm<{
    name: string;
    description: string;
    tags: string[];
    config: Record<string, any>;
  }>({
    defaultValues: async () => {
      const values = await getSchemaAndUpdateConfig(agent);
      const resolvedName = (values?.name && values.name.trim().length > 0) ? values.name : (agent.name ?? "");
      const resolvedDescription = (values?.description && values.description.trim().length > 0)
        ? values.description
        : ((agent as any).description ?? "");
      return {
        name: resolvedName,
        description: resolvedDescription,
        tags: agent.tags || [],
        config: values?.config ?? {},
      };
    },
  });

  const handleSubmit = async (data: {
    name: string;
    description: string;
    tags: string[];
    config: Record<string, any>;
  }) => {
    if (!data.name || !data.description) {
      const message = agentMessages.validation.nameDescriptionRequired();
      notify.warning(message.title, {
        description: message.description,
        key: message.key,
      });
      return;
    }

    // Store form data and show commit message dialog
    setPendingFormData(data);
    setCommitMessage("");
    setCommitMessageDialogOpen(true);
  };

  const handleSaveWithCommitMessage = async (skipCommitMessage: boolean = false) => {
    if (!pendingFormData) return;

    setCommitMessageDialogOpen(false);

    const result = await updateAgent(
      agent.assistant_id,
      agent.deploymentId,
      {
        name: pendingFormData.name,
        description: pendingFormData.description,
        config: pendingFormData.config,
        tags: pendingFormData.tags || [],
        metadata: agent.metadata || undefined,
        commitMessage: skipCommitMessage ? undefined : (commitMessage.trim() || undefined),
      },
    );

    setPendingFormData(null);
    setCommitMessage("");

    if (!result.ok) {
      const message = agentMessages.update.error();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
      return;
    }

    const message = agentMessages.update.success(pendingFormData.name);
    notify.success(message.title, {
      description: message.description,
      key: message.key,
    });

    // Invalidate caches and refresh immediately (no delay)
    try {
      invalidateAssistantListCache();
      await refreshAgents(true);
    } catch (cacheError) {
      logger.warn("Cache invalidation failed:", cacheError);
    }

    onClose();
  };

  const handleDelete = async () => {
    setDeleteSubmitting(true);
    const result = await deleteAgent(agent.deploymentId, agent.assistant_id);
    setDeleteSubmitting(false);

    if (!result.ok) {
      const message = agentMessages.delete.error();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
      return;
    }

    const message = agentMessages.delete.success();
    notify.success(message.title, {
      description: message.description,
      key: message.key,
    });

    onClose();
    refreshAgents(true); // Silent refresh - user already got success toast
  };

  const handleRevokeAccess = async () => {
    setRevokeSubmitting(true);
    const result = await revokeMyAccess(agent.assistant_id);
    setRevokeSubmitting(false);

    if (!result.ok) {
      const message = agentMessages.revoke.error();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
      return;
    }

    const message = agentMessages.revoke.success();
    notify.success(message.title, {
      description: message.description,
      key: message.key,
    });

    onClose();
    refreshAgents(true); // Silent refresh - user already got success toast
  };

  const handleVersionRestored = async () => {
    // Refresh the form with the latest config after version restore
    // Add a small delay to ensure LangGraph has finished updating
    await new Promise(resolve => setTimeout(resolve, 500));

    // Clear cached config data to ensure we fetch fresh data
    clearAgentConfigCache(agent.assistant_id);

    // First, refetch the agent to get the updated config from the server
    const agentResult = await getAgent(agent.assistant_id, agent.deploymentId);

    if (agentResult.ok && agentResult.data) {
      console.log('[handleVersionRestored] Fresh agent data:', {
        name: agentResult.data.name,
        configKeys: Object.keys(agentResult.data.config || {}),
        config: agentResult.data.config,
      });

      // Get schema with the fresh agent data
      const values = await getSchemaAndUpdateConfig(agentResult.data);

      console.log('[handleVersionRestored] Schema values:', {
        name: values.name,
        configKeys: Object.keys(values.config || {}),
        config: values.config,
      });

      // Reset form with the restored values
      form.reset({
        name: values.name,
        description: values.description || "",
        tags: agentResult.data.tags || [],
        config: values.config,
      });
    } else {
      console.warn('[handleVersionRestored] Failed to get fresh agent data:', agentResult);
      // Fallback: just reset and try to get schema with original agent
      form.reset();
      await getSchemaAndUpdateConfig(agent);
    }
  };

  return (
    <AlertDialogContent className={cn("h-auto max-h-[90vh] sm:max-w-lg md:max-w-2xl lg:max-w-3xl", ...getScrollbarClasses('y'))}>
      <form onSubmit={form.handleSubmit(handleSubmit)}>
        <AlertDialogHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <AlertDialogTitle>Edit Agent</AlertDialogTitle>
                {permissionLevel && (
                  <Badge 
                    variant={permissionLevel === 'owner' ? 'brand' : permissionLevel === 'editor' ? 'info' : 'outline'}
                    className="text-xs"
                  >
                    {permissionLevel === 'owner' && <Crown className="h-3 w-3" />}
                    {permissionLevel === 'editor' && <Edit className="h-3 w-3" />}
                    {permissionLevel === 'viewer' && <Shield className="h-3 w-3" />}
                    {permissionLevel.charAt(0).toUpperCase() + permissionLevel.slice(1)}
                  </Badge>
                )}
              </div>
              <AlertDialogDescription>
                Edit the agent for &apos;
                <span className="font-medium">{agent.graph_id}</span>&apos;
                graph.
                {!canDelete && permissionLevel === 'editor' && (
                  <span className="text-muted-foreground block mt-2">
                    You have editor access - contact the owner to delete this assistant or use "Revoke My Access" to remove your access.
                  </span>
                )}
                {!canDelete && permissionLevel === 'viewer' && (
                  <span className="text-muted-foreground block mt-2">
                    You have view-only access - use "Revoke My Access" to remove your access to this assistant.
                  </span>
                )}
              </AlertDialogDescription>
            </div>
            <AlertDialogCancel size="icon">
              <X className="size-4" />
            </AlertDialogCancel>
          </div>
        </AlertDialogHeader>
        {loading ? (
          <AgentFieldsFormLoading />
        ) : (
          <FormProvider {...form}>
            <AgentFieldsForm
              configurations={configurations}
              toolConfigurations={toolConfigurations}
              agentId={agent.assistant_id}
              ragConfigurations={ragConfigurations}
              agentsConfigurations={agentsConfigurations}
              skillsConfigurations={skillsConfigurations}
              graphId={agent.graph_id}
              assistantId={agent.assistant_id}
              permissionLevel={permissionLevel}
              onVersionRestored={handleVersionRestored}
            />
          </FormProvider>
        )}
                  <AlertDialogFooter>
            {canDelete && (
              <Button
                type="button"
                onClick={() => setDeleteConfirmDialogOpen(true)}
                className="flex w-full items-center justify-center gap-1"
                disabled={loading || deleteSubmitting}
                variant="destructive"
              >
                {deleteSubmitting ? (
                  <LoaderCircle className="animate-spin" />
                ) : (
                  <Trash />
                )}
                <span>{deleteSubmitting ? "Deleting..." : "Delete Agent"}</span>
              </Button>
            )}
            {canRevokeOwnAccess && !canDelete && (
              <Button
                onClick={handleRevokeAccess}
                className="flex w-full items-center justify-center gap-1 border-orange-500 text-orange-600 hover:bg-orange-50"
                disabled={loading || revokeSubmitting}
                variant="outline"
              >
                {revokeSubmitting ? (
                  <LoaderCircle className="animate-spin" />
                ) : (
                  <UserMinus />
                )}
                <span>{revokeSubmitting ? "Revoking..." : "Revoke My Access"}</span>
              </Button>
            )}
            <Button
              type="submit"
              className="flex w-full items-center justify-center gap-1"
              disabled={loading || form.formState.isSubmitting}
            >
              {form.formState.isSubmitting ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <Bot />
              )}
              <span>
                {form.formState.isSubmitting ? "Saving..." : "Save Changes"}
              </span>
            </Button>
          </AlertDialogFooter>
      </form>

      {/* Commit Message Modal */}
      <AlertDialog open={commitMessageDialogOpen} onOpenChange={setCommitMessageDialogOpen}>
        <AlertDialogContent className="sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>Save Changes</AlertDialogTitle>
            <AlertDialogDescription>
              Add an optional message to describe your changes. This helps track version history.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="commit-message">
                Change description <span className="text-xs text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="commit-message"
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                placeholder="e.g., Updated system prompt, Added new tools..."
                rows={3}
              />
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => {
              setPendingFormData(null);
              setCommitMessage("");
            }}>
              Cancel
            </AlertDialogCancel>
            <Button
              variant="outline"
              onClick={() => handleSaveWithCommitMessage(true)}
            >
              Skip
            </Button>
            <AlertDialogAction onClick={() => handleSaveWithCommitMessage(false)}>
              Save
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Confirmation Modal */}
      <AlertDialog open={deleteConfirmDialogOpen} onOpenChange={setDeleteConfirmDialogOpen}>
        <AlertDialogContent className="sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Agent</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{agent.name}&quot;? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setDeleteConfirmDialogOpen(false);
                handleDelete();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AlertDialogContent>
  );
}

export function EditAgentDialog({
  agent,
  open,
  onOpenChange,
}: EditAgentDialogProps) {
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
      <EditAgentDialogContent
        key={openCounter}
        agent={agent}
        onClose={() => onOpenChange(false)}
      />
    </AlertDialog>
  );
}
