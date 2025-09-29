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
import { useAgentConfig } from "@/hooks/use-agent-config";
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
  const { updateAgent, deleteAgent, revokeMyAccess } = useAgents();
  const { refreshAgents, invalidateAssistantListCache } = useAgentsContext();
  const {
    getSchemaAndUpdateConfig,

    loading,
    configurations,
    toolConfigurations,
    ragConfigurations,
    agentsConfigurations,
  } = useAgentConfig();
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [revokeSubmitting, setRevokeSubmitting] = useState(false);

  // Check user permissions
  const canDelete = canUserDeleteAssistant(agent);
  const canRevokeOwnAccess = canUserRevokeOwnAccess(agent);
  const permissionLevel = agent.permission_level;

  const form = useForm<{
    name: string;
    description: string;
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
        config: values?.config ?? {},
      };
    },
  });

  const handleSubmit = async (data: {
    name: string;
    description: string;
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

    const result = await updateAgent(
      agent.assistant_id,
      agent.deploymentId,
      data,
    );

    if (!result.ok) {
      const message = agentMessages.update.error();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
      return;
    }

    const message = agentMessages.update.success(data.name);
    notify.success(message.title, {
      description: message.description,
      key: message.key,
    });

    // Invalidate caches and refresh immediately (no delay)
    try {
      invalidateAssistantListCache();
      await refreshAgents(true);
    } catch (cacheError) {
      console.warn("Cache invalidation failed:", cacheError);
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
            />
          </FormProvider>
        )}
                  <AlertDialogFooter>
            {canDelete && (
              <Button
                onClick={handleDelete}
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
