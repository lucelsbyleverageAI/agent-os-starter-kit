"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Bot, Users, Crown, Shield } from "lucide-react";
import { cn } from "@/lib/utils";
import { GraphInfo } from "@/types/agent";
import { GraphPermissionsDialog } from "./graph-permissions-dialog";
import { canUserManageGraphAccess } from "@/lib/agent-utils";
import _ from "lodash";

interface ViewTemplatesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  graphs: GraphInfo[];
  userIsDevAdmin?: boolean;
}

export function ViewTemplatesDialog({
  open,
  onOpenChange,
  graphs,
  userIsDevAdmin = false
}: ViewTemplatesDialogProps) {
  const [selectedGraphForPermissions, setSelectedGraphForPermissions] = useState<{
    graphId: string;
    graphName: string;
  } | null>(null);

  // Filter to only show graphs that user has permissions for
  const accessibleGraphs = graphs.filter(
    (graph) => graph.user_permission_level
  );

  // Define custom order for graph templates
  const graphOrder = [
    "tools_agent",
    "deepagent",
    "deep_research_agent",
    "supervisor_agent",
    "n8n_agent",
  ];

  // Sort graphs by custom order
  const sortedGraphs = [...accessibleGraphs].sort((a, b) => {
    const indexA = graphOrder.indexOf(a.graph_id);
    const indexB = graphOrder.indexOf(b.graph_id);

    // If both are in the order array, sort by their position
    if (indexA !== -1 && indexB !== -1) {
      return indexA - indexB;
    }
    // If only A is in the order array, it comes first
    if (indexA !== -1) return -1;
    // If only B is in the order array, it comes first
    if (indexB !== -1) return 1;
    // If neither is in the order array, maintain original order
    return 0;
  });

  const handleManageAccess = (graphId: string, graphName: string) => {
    setSelectedGraphForPermissions({ graphId, graphName });
  };

  const handleClosePermissionsDialog = () => {
    setSelectedGraphForPermissions(null);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader className="pb-4">
            <DialogTitle>Agent Templates</DialogTitle>
            <DialogDescription>
              View all agent templates you have access to. Admin users can manage sharing permissions.
            </DialogDescription>
          </DialogHeader>

          {sortedGraphs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="bg-muted mx-auto flex h-16 w-16 items-center justify-center rounded-full">
                <Bot className="text-muted-foreground h-8 w-8" />
              </div>
              <h3 className="mt-4 text-lg font-semibold">No templates available</h3>
              <p className="text-muted-foreground mt-2 max-w-sm text-sm">
                You don't have permission to view any templates. Contact your admin to get access.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {sortedGraphs.map((graph) => {
                  const graphName = graph.name || _.startCase(graph.graph_id);
                  const graphDescription =
                    graph.description ||
                    `AI agent template with ${graph.assistants_count} active instance${graph.assistants_count !== 1 ? "s" : ""}`;
                  const hasAdminAccess = canUserManageGraphAccess(graph.user_permission_level, graph);

                  return (
                    <div
                      key={graph.graph_id}
                      className={cn(
                        "group relative flex flex-col gap-3 rounded-lg border p-6 transition-all",
                        "bg-card border-card-border hover:border-primary hover:shadow-lg hover:scale-[1.01]"
                      )}
                    >
                      {/* Permission Level Badge */}
                      <div className="absolute right-3 top-3">
                        <Badge variant={hasAdminAccess ? "default" : "secondary"} className="gap-1">
                          {hasAdminAccess ? (
                            <>
                              <Crown className="h-3 w-3" />
                              Admin
                            </>
                          ) : (
                            <>
                              <Shield className="h-3 w-3" />
                              Access
                            </>
                          )}
                        </Badge>
                      </div>

                      {/* Icon and title */}
                      <div className="flex items-start gap-3">
                        <div className="bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-md">
                          <Bot className="text-muted-foreground h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1 pr-16">
                          <h4 className="font-semibold leading-none">{graphName}</h4>
                          <div className="flex items-center gap-1 mt-2 text-xs text-muted-foreground">
                            <Users className="h-3 w-3" />
                            <span>
                              {graph.assistants_count} instance{graph.assistants_count !== 1 ? "s" : ""}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Description */}
                      <p className="text-muted-foreground line-clamp-3 text-sm">
                        {graphDescription}
                      </p>

                      {/* Manage Access Button - Only for admin users */}
                      {hasAdminAccess && (
                        <div className="flex items-center justify-end gap-2 mt-2 pt-3 border-t">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleManageAccess(graph.graph_id, graphName)}
                            className="gap-2"
                          >
                            <Users className="h-4 w-4" />
                            Manage Access
                          </Button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Graph Permissions Dialog */}
      {selectedGraphForPermissions && (
        <GraphPermissionsDialog
          open={!!selectedGraphForPermissions}
          onOpenChange={(open) => {
            if (!open) {
              handleClosePermissionsDialog();
            }
          }}
          graphId={selectedGraphForPermissions.graphId}
          graphName={selectedGraphForPermissions.graphName}
        />
      )}
    </>
  );
}
