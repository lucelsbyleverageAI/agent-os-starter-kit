"use client";

import { useState } from "react";
import {
  Edit,
  MessageSquare,
  MoreVertical,
  Users,
  Crown,
  Shield,
  Trash2,
  UserMinus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
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
import { isUserCreatedDefaultAssistant, canUserDeleteAssistant, canUserEditAssistant, canUserRevokeOwnAccess } from "@/lib/agent-utils";
import { useAgents } from "@/hooks/use-agents";
import { useAgentsContext } from "@/providers/Agents";
import { notify } from "@/utils/toast";
import { agentMessages } from "@/utils/toast-messages";
import { MinimalistIconButton } from "@/components/ui/minimalist-icon-button";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";

// Function to convert graph_id to human-readable name
const getGraphDisplayName = (graphId: string): string => {
  return graphId
    .replace(/_/g, ' ') // replace all underscores
    .replace(/\b\w/g, l => l.toUpperCase()); // capitalise each word
};

// Helper function to get permission icon and tooltip
function getPermissionIconAndTooltip(permissionLevel: 'owner' | 'editor' | 'viewer') {
  switch (permissionLevel) {
    case 'owner':
      return { 
        icon: Crown, 
        tooltip: 'Owner - You own this agent and can edit, delete, share with others, and manage all user permissions'
      };
    case 'editor':
      return { 
        icon: Edit, 
        tooltip: 'Editor - You can edit this agent but cannot delete it or manage sharing permissions' 
      };
    case 'viewer':
      return { 
        icon: Shield, 
        tooltip: 'Viewer - You can use this agent but cannot edit, delete, or manage permissions' 
      };
  }
}

interface AgentCardProps {
  agent: Agent;
  showDeployment?: boolean;
}

export function AgentCard({ agent, showDeployment }: AgentCardProps) {
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showSharingDialog, setShowSharingDialog] = useState(false);
  const [showDeleteConfirmation, setShowDeleteConfirmation] = useState(false);
  const [showRevokeConfirmation, setShowRevokeConfirmation] = useState(false);
  const { deleteAgent, revokeMyAccess } = useAgents();
  const { refreshAgents, invalidateAssistantListCache, invalidateAssistantCaches } = useAgentsContext();

  const isDefaultAgent = isUserCreatedDefaultAssistant(agent);
  
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

  // Use shared utility functions for consistent permission checking
  const canEdit = canUserEditAssistant(agent);
  const canShare = isDefaultAgent ? false : isOwner;
  const canDelete = canUserDeleteAssistant(agent);
  const canRevokeOwnAccess = canUserRevokeOwnAccess(agent);

  // Get permission icon and tooltip for display
  const permissionDisplay = permissionLevel ? getPermissionIconAndTooltip(permissionLevel) : null;

  return (
    <>
      <Card
        key={agent.assistant_id}
        className="overflow-hidden relative group h-44 flex flex-col transition-all duration-300 ease-out hover:border-primary hover:border-2 hover:shadow-lg hover:shadow-primary/10 vibrate-on-hover"
      >
        {/* Fixed Header - Small portion at top */}
        <CardHeader className="px-6 h-3 flex-shrink-0 flex items-center">
          <div className="flex items-center justify-between gap-3 w-full">
            <CardTitle className="text-sm font-medium text-foreground min-w-0 flex-1">
              {/* Agent Name - truncate with ellipses */}
              <span className="truncate">{agent.name}</span>
            </CardTitle>

            {/* Three-dots menu - always in same position */}
            {!isDefaultAgent && (canEdit || canShare || canDelete || canRevokeOwnAccess) && (
              <div className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
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
                      <span className="sr-only">Assistant actions</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {canEdit && (
                      <DropdownMenuItem onClick={() => setShowEditDialog(true)}>
                        <Edit className="h-4 w-4 mr-2" />
                        Edit Assistant
                      </DropdownMenuItem>
                    )}
                    {canShare && (
                      <DropdownMenuItem onClick={() => setShowSharingDialog(true)}>
                        <Users className="h-4 w-4 mr-2" />
                        Manage Access
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
                          Delete Assistant
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
          </div>
        </CardHeader>
        
        {/* Description Area - Controlled middle space */}
        <div className="px-6 flex-1 min-h-0 -mt-1">
          {(() => {
            const desc = (typeof agent.description === 'string' ? agent.description : undefined);
            return desc ? (
              <p className="text-muted-foreground text-sm leading-5 overflow-hidden text-ellipsis"
                 style={{
                   display: '-webkit-box',
                   WebkitLineClamp: 3,
                   WebkitBoxOrient: 'vertical'
                 }}>
                {desc}
              </p>
            ) : (
              <p className="text-muted-foreground/50 text-sm italic">No description</p>
            );
          })()}
        </div>
        
        {/* Fixed Footer - Small portion at bottom */}
        <CardFooter className="flex w-full justify-between items-center h-3 px-6 flex-shrink-0">
          {/* Left side: Permission, Graph, and Default badges */}
          <div className="flex items-center gap-2">
            {/* Permission Badge */}
            {permissionDisplay && (
              <MinimalistBadge
                icon={permissionDisplay.icon}
                tooltip={permissionDisplay.tooltip}
              />
            )}
            
            {/* Graph badge - always shown */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <span className="h-6 inline-flex items-center rounded-md bg-muted/50 px-2 text-xs text-muted-foreground/70 max-w-24">
                    <span className="truncate">
                      {getGraphDisplayName(agent.graph_id)}
                    </span>
                  </span>
                </TooltipTrigger>
                <TooltipContent>The template the agent belongs to: {getGraphDisplayName(agent.graph_id)}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            
            {/* Default badge */}
            {isDefaultAgent && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <span className="h-6 inline-flex items-center rounded-md bg-muted/50 px-2 text-xs text-muted-foreground/70">
                      Default
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>This is the default assistant for this graph</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
            
            {/* Warming badge */}
            {agent.schemas_warming && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <span className="h-6 inline-flex items-center rounded-md bg-orange-100 px-2 text-xs text-orange-600 animate-pulse">
                      Preparing
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>Configuration options are being prepared and will be available shortly</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>

          {/* Right side: Action Icons */}
          <div className="flex items-center gap-1">
            {canEdit && (
              <MinimalistIconButton
                icon={Edit}
                tooltip="Edit Agent"
                onClick={() => setShowEditDialog(true)}
              />
            )}
            <NextLink
              href={`/?agentId=${agent.assistant_id}&deploymentId=${agent.deploymentId}`}
            >
              <MinimalistIconButton
                icon={MessageSquare}
                tooltip="Chat to Agent"
              />
            </NextLink>
          </div>
        </CardFooter>
      </Card>

      {/* Edit Dialog */}
      {canEdit && (
        <EditAgentDialog
          agent={agent}
          open={showEditDialog}
          onOpenChange={setShowEditDialog}
        />
      )}

      {/* Sharing Dialog */}
      {canShare && (
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
