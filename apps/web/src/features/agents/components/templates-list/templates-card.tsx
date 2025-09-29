"use client";

import React, { useState, useEffect } from "react";
import { ChevronDown, ChevronRight, Crown, Shield, MoreVertical, Users, UserMinus, Network, Edit } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AgentList } from "./agent-list";
import { GraphPermissionsDialog } from "../graph-permissions-dialog";
import { cn } from "@/lib/utils";
import { Agent } from "@/types/agent";
import { Deployment } from "@/types/deployment";
import { TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { Tooltip, TooltipTrigger } from "@radix-ui/react-tooltip";
import _ from "lodash";
import { useGraphPermissions } from "@/hooks/use-graph-permissions";
import { useAgentsContext } from "@/providers/Agents";
import { useUserRole } from "@/providers/UserRole";
import { 
  canUserRevokeOwnGraphAccess, 
  canUserSeeGraphActionMenu, 
  canUserManageGraphAccess 
} from "@/lib/agent-utils";

import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { MinimalistIconButton } from "@/components/ui/minimalist-icon-button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { GraphPreviewDialog } from "@/components/graph-preview-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { useAuthContext } from "@/providers/Auth";

interface TemplateCardProps {
  deployment: Deployment;
  agents: Agent[];
  toggleGraph: (id: string) => void;
  isOpen: boolean;
  graphName?: string;
  graphDescription?: string;
}

// Helper function to get permission badge details
function getPermissionBadge(permissionLevel: 'admin' | 'access' | null) {
  switch (permissionLevel) {
    case 'admin':
      return {
        icon: Crown,
        label: 'Admin',
        className: 'bg-yellow-100 text-yellow-800 border-yellow-300',
        description: 'You have full administrative access to this agent template. You can manage permissions, view all agents, and configure settings.'
      };
    case 'access':
      return {
        icon: Shield,
        label: 'User',
        className: 'bg-blue-100 text-blue-800 border-blue-300',
        description: 'You have user access to this agent template. You can use existing agents and create new ones, but cannot manage permissions for this template.'
      };
    default:
      return null;
  }
}

export function TemplateCard({
  deployment,
  agents,
  toggleGraph,
  isOpen,
  graphName,
  graphDescription,
}: TemplateCardProps) {
  const { session } = useAuthContext();
  const graphId = agents[0].graph_id;
  const graphDeploymentId = `${deployment.id}:${graphId}`;
  const agentsCount = agents.length;
  
  // Get the graph permission level from the AgentsProvider
  const { getGraphPermissionLevel, refreshAgents } = useAgentsContext();
  const graphPermissionLevel = getGraphPermissionLevel(graphId);
  
  // Get user role information
  const { userRole, isDevAdmin } = useUserRole();
  
  // For dev admins, ensure they always have admin access even if discovery response is missing permission data
  const effectiveGraphPermissionLevel = isDevAdmin ? 'admin' : graphPermissionLevel;
  
  // Get permission management functions (only needed for revoking access)
  const { revokeMyGraphAccess } = useGraphPermissions();
  
  // Local state to track the permission level for this specific graph
  const [currentPermissionLevel, setCurrentPermissionLevel] = useState<'admin' | 'access' | null>(effectiveGraphPermissionLevel);
  const [showPermissionsModal, setShowPermissionsModal] = useState(false);
  const [revokeSubmitting, setRevokeSubmitting] = useState(false);
  const [showRevokeConfirmation, setShowRevokeConfirmation] = useState(false);
  const [showGraphPreview, setShowGraphPreview] = useState(false);
  const [showEditDetails, setShowEditDetails] = useState(false);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editName, setEditName] = useState<string>("");
  const [editDescription, setEditDescription] = useState<string>("");
  
  const permissionBadge = getPermissionBadge(currentPermissionLevel);
  
  // Permission checks
  const canSeeActionMenu = canUserSeeGraphActionMenu(currentPermissionLevel);
  const canManageAccess = canUserManageGraphAccess(currentPermissionLevel);
  const canRevokeOwnAccess = canUserRevokeOwnGraphAccess(userRole, currentPermissionLevel);
  const isAdmin = effectiveGraphPermissionLevel === 'admin';

  // Set permission level from discovery data - no need to fetch detailed permissions for display
  useEffect(() => {
    // Always use the permission level from discovery data for display purposes
    // The permissions management endpoint is only needed when actually managing access
    setCurrentPermissionLevel(effectiveGraphPermissionLevel);
  }, [effectiveGraphPermissionLevel]);

  const handleManageAccess = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setShowPermissionsModal(true);
  };

  const handleOpenEditDetails = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Pre-fill from discovery when available (name/description not present in this component props, so use defaults)
    const defaultName = _.startCase(graphId);
    setEditName(graphName || defaultName);
    setEditDescription(graphDescription || "");
    setShowEditDetails(true);
  };

  const submitGraphDetails = async () => {
    setEditSubmitting(true);
    try {
      // Proxy to LangConnect API via generic proxy route
      const basePath = `/api/langconnect/agents/graphs/${graphId}`;
      const res = await fetch(basePath, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...(session?.accessToken ? { 'Authorization': `Bearer ${session.accessToken}` } : {}),
        },
        body: JSON.stringify({ name: editName, description: editDescription })
      });
      if (!res.ok) {
        throw new Error(`Failed to update graph details: ${res.status}`);
      }
      // Refresh agents list (bypass cache)
      await refreshAgents(true);
      setShowEditDetails(false);
    } catch (err) {
      console.error(err);
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleRevokeMyAccess = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    setShowRevokeConfirmation(true);
  };

  const confirmRevokeAccess = async () => {
    setShowRevokeConfirmation(false);
    setRevokeSubmitting(true);
    try {
      const success = await revokeMyGraphAccess(graphId);
      if (success) {
        // Refresh the agents list so this graph disappears - silent since user already got success toast
        refreshAgents(true);
      }
    } catch (error) {
      console.error('Error revoking graph access:', error);
    } finally {
      setRevokeSubmitting(false);
    }
  };

  return (
    <>
      <Card
        className={cn(
          "overflow-hidden",
          isOpen ? "" : "hover:bg-accent/50 cursor-pointer transition-colors",
        )}
        onClick={() => {
          // Don't allow toggling via clicking the card if it's already open
          if (isOpen) return;
          toggleGraph(graphDeploymentId);
        }}
      >
        <Collapsible
          open={isOpen}
          onOpenChange={() => toggleGraph(graphDeploymentId)}
        >
          <CardHeader className="flex flex-row items-center bg-inherit">
            <div className="flex-1">
              <div className="flex items-center">
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mr-2 h-8 w-8 p-0"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      toggleGraph(graphDeploymentId);
                    }}
                  >
                    {isOpen ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                    <span className="sr-only">Toggle</span>
                  </Button>
                </CollapsibleTrigger>
                <CardTitle className="flex flex-col gap-1">
                  <p className="text-2xl">{graphName || _.startCase(graphId)}</p>
                  {graphDescription ? (
                    <span className="text-muted-foreground text-sm font-normal leading-5">{graphDescription}</span>
                  ) : null}
                </CardTitle>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* Permission Badge */}
              {permissionBadge && (
                <MinimalistBadge
                  icon={permissionBadge.icon}
                  tooltip={permissionBadge.description}
                />
              )}
              
              {/* Graph Preview Button */}
              <div onClick={(e) => e.stopPropagation()}>
                <MinimalistIconButton
                  icon={Network}
                  tooltip="View Agent Template Workflow"
                  onClick={() => setShowGraphPreview(true)}
                />
              </div>
              
              {/* Agents Count Badge */}
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <span className="h-6 inline-flex items-center rounded-md bg-muted/50 px-2 text-xs text-muted-foreground/70">
                      {agentsCount} Agent{agentsCount === 1 ? "" : "s"}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    This graph contains {agentsCount} agent{agentsCount === 1 ? "" : "s"}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>

              {/* Graph Actions Menu */}
              {canSeeActionMenu && (
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
                      <span className="sr-only">Graph actions</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {canManageAccess && (
                      <DropdownMenuItem onClick={handleManageAccess}>
                        <Users className="h-4 w-4 mr-2" />
                        Manage Access
                      </DropdownMenuItem>
                    )}
                    {isAdmin && (
                      <DropdownMenuItem onClick={handleOpenEditDetails}>
                        <Edit className="h-4 w-4 mr-2" />
                        Edit Graph Details
                      </DropdownMenuItem>
                    )}
                    {canRevokeOwnAccess && (
                      <DropdownMenuItem 
                        onClick={handleRevokeMyAccess}
                        className="text-red-600 focus:text-red-600"
                        disabled={revokeSubmitting}
                      >
                        <UserMinus className="h-4 w-4 mr-2" />
                        {revokeSubmitting ? 'Revoking...' : 'Revoke My Access'}
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </CardHeader>
          <CollapsibleContent>
            <CardContent className="pt-6">
              <AgentList
                agents={agents}
                deploymentId={deployment.id}
              />
            </CardContent>
          </CollapsibleContent>
        </Collapsible>
      </Card>

      {/* Graph Permissions Management Modal */}
      {showPermissionsModal && (
        <GraphPermissionsDialog
          open={showPermissionsModal}
          onOpenChange={setShowPermissionsModal}
          graphId={graphId}
          graphName={_.startCase(graphId)}
        />
      )}

      {/* Revoke Access Confirmation Dialog */}
      <ConfirmationDialog
        open={showRevokeConfirmation}
        onOpenChange={setShowRevokeConfirmation}
        onConfirm={confirmRevokeAccess}
        title="Revoke Graph Access"
        description={`Are you sure you want to remove your access to "${_.startCase(graphId)}"? You will no longer be able to view or use assistants in this graph.`}
        confirmText="Revoke Access"
        variant="default"
      />

      {/* Graph Preview Dialog */}
      <GraphPreviewDialog
        open={showGraphPreview}
        onOpenChange={setShowGraphPreview}
        graphId={graphId}
        assistantId={agents[0]?.assistant_id || ''}
        deploymentId={deployment.id}
      />

      {/* Edit Graph Details Dialog (Admin only) */}
      <Dialog open={showEditDetails} onOpenChange={setShowEditDetails}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit Graph Details</DialogTitle>
            <DialogDescription>Update the display name and description for this template.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <label className="text-sm font-medium">Name</label>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} placeholder={_.startCase(graphId)} />
            </div>
            <div>
              <label className="text-sm font-medium">Description</label>
              <Textarea value={editDescription} onChange={(e) => setEditDescription(e.target.value)} placeholder={`Describe ${_.startCase(graphId)}`} rows={4} />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowEditDetails(false)} disabled={editSubmitting}>Cancel</Button>
              <Button onClick={submitGraphDetails} disabled={editSubmitting || !editName.trim()}>{editSubmitting ? 'Saving...' : 'Save'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
