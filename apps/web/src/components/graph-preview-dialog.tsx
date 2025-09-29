import React, { useEffect, useState } from 'react';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { X, Loader2 } from "lucide-react";

import { useGraphSchema } from "@/hooks/use-graph-schema";
import { GraphVisualization } from "./graph-visualization";
import _ from "lodash";

interface GraphPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  graphId: string;
  assistantId: string;
  deploymentId: string;
}

export function GraphPreviewDialog({
  open,
  onOpenChange,
  graphId,
  assistantId,
  deploymentId,
}: GraphPreviewDialogProps) {
  const { getGraphSchema, loading } = useGraphSchema();
  const [schema, setSchema] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch graph schema when dialog opens
  useEffect(() => {
    if (open && assistantId && deploymentId) {
      const fetchSchema = async () => {
        setError(null);
        try {
          const result = await getGraphSchema(assistantId, deploymentId, true);
          if (result) {
            setSchema(result);
          } else {
            setError("Failed to load graph schema");
          }
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to load graph schema");
        }
      };
      
      fetchSchema();
    }
  }, [open, assistantId, deploymentId, getGraphSchema]);

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setSchema(null);
      setError(null);
    }
  }, [open]);

  const graphDisplayName = _.startCase(graphId);

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent 
        className="h-auto max-h-[90vh] sm:max-w-lg md:max-w-4xl lg:max-w-5xl xl:max-w-6xl overflow-y-auto"
      >
        <AlertDialogHeader>
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1.5">
              <AlertDialogTitle className="text-xl">
                {graphDisplayName} Workflow
              </AlertDialogTitle>
              <AlertDialogDescription className="text-sm text-muted-foreground">
                View the agent template workflow and execution flow. This diagram shows how data flows through the different nodes in your agent.
              </AlertDialogDescription>
            </div>
            <AlertDialogCancel asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <X className="h-4 w-4" />
                <span className="sr-only">Close</span>
              </Button>
            </AlertDialogCancel>
          </div>
        </AlertDialogHeader>

        <div className="w-full" style={{ height: '70vh' }}>
          {loading && (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-3">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                <p className="text-sm text-muted-foreground">Loading workflow...</p>
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-3 text-center">
                <div className="rounded-full bg-destructive/10 p-3">
                  <X className="h-6 w-6 text-destructive" />
                </div>
                <div>
                  <p className="text-sm font-medium">Failed to load workflow</p>
                  <p className="text-xs text-muted-foreground mt-1">{error}</p>
                </div>
              </div>
            </div>
          )}

          {schema && !loading && !error && (
            <div className="h-full rounded-lg bg-gray-50">
              <GraphVisualization 
                schema={schema} 
                className="h-full"
              />
            </div>
          )}

          {!schema && !loading && !error && (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-3">
                <div className="rounded-full bg-muted p-3">
                  <X className="h-6 w-6 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">No workflow data available</p>
              </div>
            </div>
          )}
        </div>

        {schema && (
          <div className="border-t pt-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {schema.nodes?.length || 0} nodes, {schema.edges?.length || 0} edges
              </span>
              <span>
                Use mouse wheel to zoom • Drag to pan • Click and drag nodes to rearrange
              </span>
            </div>
          </div>
        )}
      </AlertDialogContent>
    </AlertDialog>
  );
} 