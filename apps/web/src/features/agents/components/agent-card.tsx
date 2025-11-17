"use client";

import { useState } from "react";
import {
  Bot,
  Copy,
  Edit,
  LoaderCircle,
  MessageSquare,
  MoreVertical,
  Users,
  Trash2,
  UserMinus,
  Star,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Agent } from "@/types/agent";
import { EditAgentDialog } from "./create-edit-agent-dialogs/edit-agent-dialog";
import { AssistantSharingDialog } from "./assistant-sharing-dialog";
import NextLink from "next/link";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { isUserDefaultAssistant, canUserDeleteAssistant, canUserEditAssistant, canUserRevokeOwnAccess } from "@/lib/agent-utils";
import { useAgents } from "@/hooks/use-agents";
import { useAgentsContext } from "@/providers/Agents";
import { useAuthContext } from "@/providers/Auth";
import { notify, rawToast } from "@/utils/toast";
import { agentMessages } from "@/utils/toast-messages";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { getTagLabel } from "@/lib/agent-tags";
import { logger } from "@/lib/logger";

// Minimal agent type for display - matches what AgentCard actually uses
type MinimalAgentForCard = {
  assistant_id: string;
  deploymentId: string;
  name: string;
  description?: string;
  tags?: string[];
  graph_id: string;
  permission_level?: 'owner' | 'editor' | 'viewer' | 'admin';
  allowed_actions?: string[];
  metadata?: any;
};

interface AgentCardProps {
  agent: Agent | MinimalAgentForCard;
  showDeployment?: boolean;
}

// Helper function to truncate long names
function truncateName(name: string, maxLength: number = 40): { truncated: boolean; displayName: string } {
  if (name.length <= maxLength) {
    return { truncated: false, displayName: name };
  }
  return {
    truncated: true,
    displayName: name.substring(0, maxLength) + "..."
  };
}

export function AgentCard({ agent, showDeployment }: AgentCardProps) {
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showSharingDialog, setShowSharingDialog] = useState(false);
  const [showDeleteConfirmation, setShowDeleteConfirmation] = useState(false);
  const [showRevokeConfirmation, setShowRevokeConfirmation] = useState(false);
  const [isHydrating, setIsHydrating] = useState(false);
  const [isDuplicating, setIsDuplicating] = useState(false);
  const [isSettingDefault, setIsSettingDefault] = useState(false);
  const { session } = useAuthContext();
  const { getAgent, createAgent, deleteAgent, revokeMyAccess } = useAgents();
  const { refreshAgents, invalidateAssistantListCache, invalidateAssistantCaches, invalidateAllAssistantCaches, addAgentToList, defaultAssistant, setDefaultAssistant, refreshDefaultAssistant, hydrateAgent } = useAgentsContext();

  const isDefaultAgent = isUserDefaultAssistant(agent);
  const isUserDefault = defaultAssistant?.assistant_id === agent.assistant_id;

  // Get permission information from agent metadata
  const permissionLevel = agent.permission_level as 'owner' | 'editor' | 'viewer' | undefined;
  const isOwner = permissionLevel === 'owner';

  const handleDeleteAgent = async () => {
    setShowDeleteConfirmation(false);
    const result = await deleteAgent(agent.deploymentId, agent.assistant_id);
    if (result.ok) {
      const message = agentMessages.delete.success();
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });

      // Invalidate specific assistant caches
      invalidateAssistantCaches(agent.assistant_id);

      // Invalidate assistant list cache (where the deleted agent would be listed)
      invalidateAssistantListCache();

      // Refresh default assistant (in case it was auto-reassigned)
      await refreshDefaultAssistant();

      // Refresh agents list - silent since user already got success toast
      refreshAgents(true);
    } else {
      const message = agentMessages.delete.error();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
    }
  };

  const handleRevokeAccess = async () => {
    setShowRevokeConfirmation(false);
    const result = await revokeMyAccess(agent.assistant_id);
    if (result.ok) {
      const message = agentMessages.revoke.success();
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });

      // Invalidate specific assistant caches
      invalidateAssistantCaches(agent.assistant_id);

      // Invalidate assistant list cache (where the revoked agent would be removed)
      invalidateAssistantListCache();

      // Refresh default assistant (in case it was auto-reassigned)
      await refreshDefaultAssistant();

      // Refresh agents list - silent since user already got success toast
      refreshAgents(true);
    } else {
      const message = agentMessages.revoke.error();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
    }
  };

  const handleSetDefault = async () => {
    setIsSettingDefault(true);
    try {
      const result = await setDefaultAssistant(agent.assistant_id);
      if (result.ok) {
        // Refresh default assistant state to ensure UI updates
        await refreshDefaultAssistant();

        notify.success("Default Assistant Set", {
          description: `${agent.name} is now your default assistant`,
        });
      } else {
        notify.error("Failed to Set Default", {
          description: result.errorMessage || "Could not set default assistant",
        });
      }
    } finally {
      setIsSettingDefault(false);
    }
  };

  const handleEditClick = async () => {
    // Check if agent needs hydration (doesn't have config field)
    const needsHydration = !('config' in agent);

    if (needsHydration) {
      setIsHydrating(true);
      try {
        await hydrateAgent(agent.assistant_id);
        setShowEditDialog(true);
      } catch (error) {
        logger.error('[AgentCard] Failed to hydrate agent:', error);
        notify.error("Failed to Load", {
          description: "Could not load agent configuration. Please try again.",
        });
      } finally {
        setIsHydrating(false);
      }
    } else {
      setShowEditDialog(true);
    }
  };

  const handleManageAccessClick = async () => {
    // Check if agent needs hydration (doesn't have config field)
    const needsHydration = !('config' in agent);

    if (needsHydration) {
      setIsHydrating(true);
      try {
        await hydrateAgent(agent.assistant_id);
        setShowSharingDialog(true);
      } catch (error) {
        logger.error('[AgentCard] Failed to hydrate agent:', error);
        notify.error("Failed to Load", {
          description: "Could not load agent configuration. Please try again.",
        });
      } finally {
        setIsHydrating(false);
      }
    } else {
      setShowSharingDialog(true);
    }
  };

  const handleDuplicateAgent = async () => {
    setIsDuplicating(true);
    // Show loading toast
    const toastId = rawToast.loading("Duplicating Agent", {
      description: `Creating a copy of "${agent.name}"...`,
    });

    try {
      // Fetch full agent data (including config)
      const fullAgentResult = await getAgent(agent.assistant_id, agent.deploymentId);

      if (!fullAgentResult.ok || !fullAgentResult.data) {
        throw new Error("Failed to fetch agent configuration");
      }

      const originalAgent = fullAgentResult.data;

      // Handle long agent names (LangGraph has 255 char limit)
      const MAX_NAME_LENGTH = 255;
      const COPY_SUFFIX = " - Copy";
      const maxOriginalLength = MAX_NAME_LENGTH - COPY_SUFFIX.length;

      let duplicateName = `${agent.name}${COPY_SUFFIX}`;
      if (duplicateName.length > MAX_NAME_LENGTH) {
        duplicateName = `${agent.name.substring(0, maxOriginalLength)}...${COPY_SUFFIX}`;
      }

      // Create duplicate with modified name
      const result = await createAgent(
        agent.deploymentId,
        agent.graph_id,
        {
          name: duplicateName,
          description: originalAgent.description || "",
          config: originalAgent.config || {},
          tags: originalAgent.tags || [],
          // Exclude owner-specific metadata
          metadata: {},
        }
      );

      if (!result.ok) {
        throw new Error(result.errorMessage || "Failed to duplicate agent");
      }

      // Dismiss loading toast
      rawToast.dismiss(toastId);

      // Show success notification
      const message = agentMessages.duplicate.success(duplicateName);
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });

      // Optimistically add to agent list
      const newAgent = result.data!;
      addAgentToList({
        ...newAgent,
        deploymentId: agent.deploymentId,
        permission_level: "owner",
        allowed_actions: ["view", "chat", "edit", "delete", "share", "manage_access"],
        owner_id: session?.user?.id || "",
        owner_display_name: "You",
      });

      // Invalidate and refresh
      invalidateAssistantListCache();
      invalidateAllAssistantCaches();
      await refreshAgents(true);

    } catch (error) {
      // Dismiss loading toast
      rawToast.dismiss(toastId);

      // Show error notification
      const message = agentMessages.duplicate.error();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });

      logger.error("Failed to duplicate agent:", error);
    } finally {
      setIsDuplicating(false);
    }
  };

  // Type guard to check if agent is full Agent (has config)
  const isFullAgent = (a: Agent | MinimalAgentForCard): a is Agent => {
    return 'config' in a;
  };

  // Use shared utility functions for consistent permission checking
  const canEdit = canUserEditAssistant(agent);
  const canShare = isDefaultAgent ? false : isOwner;
  const canDelete = canUserDeleteAssistant(agent);
  const canRevokeOwnAccess = canUserRevokeOwnAccess(agent);

  return (
    <>
      <Card
        key={agent.assistant_id}
        className="group relative flex flex-col items-start gap-3 p-6 transition-all hover:border-primary hover:shadow-lg hover:scale-[1.01] vibrate-on-hover"
      >
        {/* Three-dots menu - absolute positioned in top-right */}
        {!isDefaultAgent && (canEdit || canShare || canDelete || canRevokeOwnAccess) && (
          <div className="absolute right-3 top-3 opacity-0 group-hover:opacity-100 transition-opacity">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                  }}
                >
                  <MoreVertical className="h-4 w-4" />
                  <span className="sr-only">Agent actions</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {canEdit && (
                  <DropdownMenuItem onClick={handleEditClick} disabled={isHydrating}>
                    {isHydrating ? (
                      <LoaderCircle className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Edit className="h-4 w-4 mr-2" />
                    )}
                    Edit Agent
                  </DropdownMenuItem>
                )}
                {canShare && (
                  <DropdownMenuItem onClick={handleManageAccessClick} disabled={isHydrating}>
                    {isHydrating ? (
                      <LoaderCircle className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Users className="h-4 w-4 mr-2" />
                    )}
                    Manage Access
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={handleDuplicateAgent} disabled={isDuplicating}>
                  {isDuplicating ? (
                    <LoaderCircle className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Copy className="h-4 w-4 mr-2" />
                  )}
                  Duplicate Agent
                </DropdownMenuItem>
                {!isDefaultAgent && !isUserDefault && (
                  <DropdownMenuItem onClick={handleSetDefault} disabled={isSettingDefault}>
                    {isSettingDefault ? (
                      <LoaderCircle className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Star className="h-4 w-4 mr-2" />
                    )}
                    Set as Default
                  </DropdownMenuItem>
                )}
                {canDelete && (
                  <>
                    {(canEdit || canShare) && <DropdownMenuSeparator />}
                    <DropdownMenuItem
                      onClick={() => setShowDeleteConfirmation(true)}
                      className="text-red-600 focus:text-red-600"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Delete Agent
                    </DropdownMenuItem>
                  </>
                )}
                {canRevokeOwnAccess && !canDelete && (
                  <>
                    {(canEdit || canShare) && <DropdownMenuSeparator />}
                    <DropdownMenuItem
                      onClick={() => setShowRevokeConfirmation(true)}
                      className="text-orange-600 focus:text-orange-600"
                    >
                      <UserMinus className="h-4 w-4 mr-2" />
                      Revoke My Access
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}

        {/* Icon and title */}
        <div className="flex items-center gap-3 w-full">
          <div className="bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-md">
            <Bot className="text-muted-foreground h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1 flex items-center gap-2">
            {(() => {
              const { truncated, displayName } = truncateName(agent.name);

              return truncated ? (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <h4 className="font-semibold leading-none">{displayName}</h4>
                    </TooltipTrigger>
                    <TooltipContent>
                      <span>{agent.name}</span>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              ) : (
                <h4 className="font-semibold leading-none">{displayName}</h4>
              );
            })()}
            {isUserDefault && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                  </TooltipTrigger>
                  <TooltipContent>
                    <span>Default Assistant - Auto-loads when you open chat</span>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
        </div>

        {/* Description - Fixed 3 lines */}
        <p className="text-muted-foreground line-clamp-3 text-sm w-full min-h-[3.75rem]">
          {agent.description || "No description provided"}
        </p>

        {/* Divider */}
        <div className="w-full border-t border-border" />

        {/* Footer action bar */}
        <div className="flex w-full items-center justify-between gap-3">
          {/* Left side: Tags */}
          <div className="flex items-center gap-2 flex-1 min-w-0 max-w-[60%]">
            {agent.tags && agent.tags.length > 0 ? (
              <>
                {agent.tags.slice(0, 1).map((tag) => (
                  <TooltipProvider key={tag}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <div className="max-w-[150px]">
                          <Badge variant="outline" className="text-xs truncate block">
                            <span className="truncate block">{getTagLabel(tag)}</span>
                          </Badge>
                        </div>
                      </TooltipTrigger>
                      <TooltipContent>
                        <span>{getTagLabel(tag)}</span>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                ))}
                {agent.tags.length > 1 && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <Badge variant="secondary" className="text-xs">
                          +{agent.tags.length - 1}
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        <div className="flex flex-col gap-1">
                          {agent.tags.slice(1).map((tag) => (
                            <span key={tag}>{getTagLabel(tag)}</span>
                          ))}
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}
              </>
            ) : (
              <div className="text-xs text-muted-foreground">No tags</div>
            )}
          </div>

          {/* Right side: Action buttons */}
          <div className="flex items-center gap-2 shrink-0">
            {canEdit && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleEditClick}
                disabled={isHydrating}
                className="h-8 cursor-pointer"
              >
                {isHydrating ? (
                  <LoaderCircle className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                ) : (
                  <Edit className="h-3.5 w-3.5 mr-1.5" />
                )}
                Edit
              </Button>
            )}
            <NextLink href={`/?agentId=${agent.assistant_id}&deploymentId=${agent.deploymentId}`} className="cursor-pointer">
              <Button
                variant="default"
                size="sm"
                className="h-8 cursor-pointer"
              >
                <MessageSquare className="h-3.5 w-3.5 mr-1.5" />
                Chat
              </Button>
            </NextLink>
          </div>
        </div>
      </Card>

      {/* Edit Dialog - Agent will be hydrated by handleEditClick before opening */}
      {canEdit && (
        <EditAgentDialog
          agent={agent as Agent}
          open={showEditDialog}
          onOpenChange={setShowEditDialog}
        />
      )}

      {/* Sharing Dialog - only render if agent is hydrated */}
      {canShare && isFullAgent(agent) && (
        <AssistantSharingDialog
          assistant={agent}
          open={showSharingDialog}
          onOpenChange={setShowSharingDialog}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmationDialog
        open={showDeleteConfirmation}
        onOpenChange={setShowDeleteConfirmation}
        onConfirm={handleDeleteAgent}
        title="Delete Agent"
        description={`Are you sure you want to delete "${agent.name}"? This action cannot be undone.`}
        confirmText="Delete"
        variant="destructive"
      />

      {/* Revoke Access Confirmation Dialog */}
      <ConfirmationDialog
        open={showRevokeConfirmation}
        onOpenChange={setShowRevokeConfirmation}
        onConfirm={handleRevokeAccess}
        title="Revoke Access"
        description={`Remove your access to "${agent.name}"? You'll need to be re-invited to use this assistant again.`}
        confirmText="Revoke Access"
        variant="default"
      />
    </>
  );
}
