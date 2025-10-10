"use client";

import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PublicGraphPermission, PublicAssistantPermission, PublicCollectionPermission } from "@/types/public-permissions";
import { useAgentsContext } from "@/providers/Agents";
import { useKnowledgeContext } from "@/features/knowledge/providers/Knowledge";

interface AddPermissionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (type: 'graph' | 'assistant' | 'collection', id: string, permissionLevel: string) => void;
  isLoading: boolean;
  type: 'graph' | 'assistant' | 'collection';
  existingGraphPermissions: PublicGraphPermission[];
  existingAssistantPermissions: PublicAssistantPermission[];
  existingCollectionPermissions: PublicCollectionPermission[];
}

export const AddPermissionModal = ({
  isOpen,
  onClose,
  onConfirm,
  isLoading,
  type,
  existingGraphPermissions,
  existingAssistantPermissions,
  existingCollectionPermissions,
}: AddPermissionModalProps) => {
  const [selectedId, setSelectedId] = useState("");
  const [permissionLevel, setPermissionLevel] = useState("");
  const { displayItems, discoveryData } = useAgentsContext();
  const { collections } = useKnowledgeContext();

  const handleSubmit = () => {
    if (selectedId && permissionLevel) {
      onConfirm(type, selectedId, permissionLevel);
    }
  };

  const handleClose = () => {
    setSelectedId("");
    setPermissionLevel("");
    onClose();
  };

  useEffect(() => {
    // Set default permission level when type changes
    if (type === 'graph') {
      setPermissionLevel('access');
    } else if (type === 'assistant') {
      setPermissionLevel('viewer');
    } else if (type === 'collection') {
      setPermissionLevel('viewer');
    }
  }, [type]);

  // Get existing IDs to filter out items that already have permissions
  const existingGraphIds = new Set(existingGraphPermissions.map(p => p.graph_id));
  const existingAssistantIds = new Set(existingAssistantPermissions.map(p => p.assistant_id));
  const existingCollectionIds = new Set(existingCollectionPermissions.map(p => p.collection_id));

  // For assistants, also get graph IDs that have public permissions 
  // (since default assistants in those graphs don't need separate permissions)
  const publicGraphIds = new Set(existingGraphPermissions.map(p => p.graph_id));

  // Helper function to convert graph_id to human-readable name
  const getGraphDisplayName = (graphId: string): string => {
    const named = discoveryData?.valid_graphs?.find(g => g.graph_id === graphId)?.name;
    if (named && named.trim()) return named;
    return graphId.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  // Group assistants by graph for better organization
  const groupedAssistantOptions = React.useMemo(() => {
    if (type !== 'assistant') return {};
    
    const assistantOptions = displayItems
      .filter((item: any) => item.type === 'assistant')
      .filter((item: any) => {
        // Exclude assistants that already have direct public permissions
        if (existingAssistantIds.has(item.assistant_id!)) {
          return false;
        }
        
        // Exclude default assistants whose graphs already have public permissions
        if (item.metadata?.created_by === 'system' && item.graph_id && publicGraphIds.has(item.graph_id)) {
          return false;
        }
        
        return true;
      })
      .map((item: any) => ({
        id: item.assistant_id!,
        name: item.name,
        type: 'assistant' as const,
        graph_id: item.graph_id,
        is_default: item.metadata?.created_by === 'system'
      }));

    // Group by graph_id
    const grouped: { [key: string]: any[] } = {};
    assistantOptions.forEach(option => {
      const graphId = option.graph_id || 'unknown';
      if (!grouped[graphId]) {
        grouped[graphId] = [];
      }
      grouped[graphId].push(option);
    });

    // Sort assistants within each group (default assistants first)
    Object.keys(grouped).forEach(graphId => {
      grouped[graphId].sort((a, b) => {
        if (a.is_default && !b.is_default) return -1;
        if (!a.is_default && b.is_default) return 1;
        return a.name.localeCompare(b.name);
      });
    });

    return grouped;
  }, [type, displayItems, existingAssistantIds, publicGraphIds]);

  // Get available options based on type
  const getAvailableOptions = () => {
    switch (type) {
      case 'graph':
        return (discoveryData?.valid_graphs || [])
          .filter((graph: any) => !existingGraphIds.has(graph.graph_id))
          .map((graph: any) => ({
            id: graph.graph_id,
            name: getGraphDisplayName(graph.graph_id),
            type: 'graph' as const
          }));
      
      case 'collection':
        return collections
          .filter(collection => !existingCollectionIds.has(collection.uuid))
          .map(collection => ({
            id: collection.uuid,
            name: collection.name,
            type: 'collection' as const
          }));
      
      case 'assistant':
      default:
        return []; // For assistants, we use the grouped structure
    }
  };

  const availableOptions = getAvailableOptions();

  // Debug logging when modal opens
  useEffect(() => {
    if (isOpen) {
      console.log('[AddPermissionModal] Modal opened', {
        type,
        discoveryData: {
          hasData: !!discoveryData,
          validGraphs: discoveryData?.valid_graphs?.length || 0,
          graphIds: discoveryData?.valid_graphs?.map(g => g.graph_id) || [],
          graphNames: discoveryData?.valid_graphs?.map(g => ({ id: g.graph_id, name: g.name })) || [],
        },
        existingPermissions: {
          graphs: existingGraphPermissions.length,
          graphIds: existingGraphPermissions.map(p => p.graph_id),
          assistants: existingAssistantPermissions.length,
          collections: existingCollectionPermissions.length,
        },
        filtering: {
          type,
          availableOptionsCount: type === 'assistant' ? Object.keys(groupedAssistantOptions).length : availableOptions.length,
          availableOptions: type === 'graph' ? availableOptions : type === 'assistant' ? Object.keys(groupedAssistantOptions) : availableOptions.map(o => o.id),
        }
      });

      if (type === 'graph') {
        console.log('[AddPermissionModal] Graph filtering details:', {
          totalGraphsInDiscovery: discoveryData?.valid_graphs?.length || 0,
          graphsWithPublicPermissions: existingGraphIds.size,
          graphsAfterFiltering: availableOptions.length,
          allGraphs: discoveryData?.valid_graphs?.map(g => ({
            id: g.graph_id,
            name: g.name || 'unnamed',
            hasPublicPermission: existingGraphIds.has(g.graph_id)
          })) || []
        });
      }
    }
  }, [isOpen, type, discoveryData, existingGraphPermissions, existingAssistantPermissions, existingCollectionPermissions, availableOptions, groupedAssistantOptions, existingGraphIds]);

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Add Public {type === 'graph' ? 'Graph' : type === 'assistant' ? 'Assistant' : 'Collection'} Permission</DialogTitle>
          <DialogDescription asChild>
            <div>
              Grant public access to a {type}. This will make it accessible to all users.
              {type === 'assistant' && (
                <div className="mt-2 text-sm text-muted-foreground">
                  <strong>Note:</strong> Default assistants in graphs with public permissions are automatically accessible and don't need separate permissions.
                </div>
              )}
            </div>
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="item-select">
              Select {type === 'graph' ? 'Graph' : type === 'assistant' ? 'Assistant' : 'Collection'}
            </Label>
            <Select
              value={selectedId}
              onValueChange={setSelectedId}
              disabled={isLoading}
            >
              <SelectTrigger>
                <SelectValue placeholder={`Choose a ${type}...`} />
              </SelectTrigger>
              <SelectContent>
                {type === 'assistant' ? (
                  // Grouped sections for assistants
                  Object.keys(groupedAssistantOptions).length === 0 ? (
                    <SelectItem value="__no_options__" disabled>
                      No assistants available (all covered by graph permissions or already public)
                    </SelectItem>
                  ) : (
                    Object.entries(groupedAssistantOptions).map(([graphId, assistants]) => (
                      <React.Fragment key={graphId}>
                        {/* Graph section header */}
                        <div className="px-2 py-1.5 text-sm font-medium text-muted-foreground bg-muted/50">
                          {getGraphDisplayName(graphId)}
                        </div>
                        
                        {/* Assistants in this graph */}
                        {assistants.map((assistant: any) => (
                          <SelectItem key={assistant.id} value={assistant.id}>
                            <div className="flex flex-col">
                              <div className="flex items-center gap-2">
                                <span>{assistant.name}</span>
                                {assistant.is_default && (
                                  <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                                    Default
                                  </span>
                                )}
                              </div>
                              <span className="text-xs text-muted-foreground">
                                {assistant.id}
                              </span>
                            </div>
                          </SelectItem>
                        ))}
                      </React.Fragment>
                    ))
                  )
                ) : (
                  // Simple list for graphs and collections
                  availableOptions.length === 0 ? (
                    <SelectItem value="__no_options__" disabled>
                      All {type}s already have public permissions
                    </SelectItem>
                  ) : (
                    availableOptions.map((option: any) => (
                      <SelectItem key={option.id} value={option.id}>
                        {option.name}
                      </SelectItem>
                    ))
                  )
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="permission-select">Permission Level</Label>
            <Select
              value={permissionLevel}
              onValueChange={setPermissionLevel}
              disabled={isLoading}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {type === 'graph' ? (
                  <>
                    <SelectItem value="access">Access</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                  </>
                ) : type === 'assistant' ? (
                  <>
                    <SelectItem value="viewer">Viewer</SelectItem>
                    <SelectItem value="editor">Editor</SelectItem>
                  </>
                ) : (
                  <>
                    <SelectItem value="viewer">Viewer</SelectItem>
                    <SelectItem value="editor">Editor</SelectItem>
                  </>
                )}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button 
            onClick={handleSubmit} 
            disabled={
              isLoading || 
              !selectedId || 
              (type === 'assistant' 
                ? Object.keys(groupedAssistantOptions).length === 0 
                : availableOptions.length === 0
              )
            }
          >
            {isLoading ? "Adding..." : "Add Permission"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}; 