"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Memory } from "@/types/memory";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { format } from "date-fns";

interface ViewPayloadDialogProps {
  memory: Memory | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ViewPayloadDialog({ memory, open, onOpenChange }: ViewPayloadDialogProps) {
  if (!memory) return null;

  const formatDate = (dateString: string | undefined) => {
    if (!dateString) return 'N/A';
    try {
      return format(new Date(dateString), "MMMM d, yyyy 'at' h:mm a");
    } catch {
      return dateString;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>Memory Details</DialogTitle>
          <DialogDescription>
            Complete information about this memory, including metadata and system data.
          </DialogDescription>
        </DialogHeader>
        
        <ScrollArea className="max-h-[60vh] pr-4">
          <div className="space-y-6">
            {/* Memory Content */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">Memory Content</h4>
              <div className="p-3 bg-muted rounded-md">
                <p className="text-sm whitespace-pre-wrap">{memory.memory}</p>
              </div>
            </div>

            {/* Basic Information */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium">Basic Information</h4>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <span className="text-xs text-muted-foreground">Memory ID</span>
                  <p className="text-sm font-mono bg-muted px-2 py-1 rounded text-xs">
                    {memory.id}
                  </p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Hash</span>
                  <p className="text-sm font-mono bg-muted px-2 py-1 rounded text-xs">
                    {memory.hash}
                  </p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Created</span>
                  <p className="text-sm">{formatDate(memory.created_at)}</p>
                </div>
                <div>
                  <span className="text-xs text-muted-foreground">Updated</span>
                  <p className="text-sm">{formatDate(memory.updated_at)}</p>
                </div>
              </div>
            </div>

            {/* Context Information */}
            {(memory.payload?.agent_id || memory.payload?.run_id) && (
              <div className="space-y-3">
                <h4 className="text-sm font-medium">Context Information</h4>
                <div className="grid grid-cols-1 gap-3">
                  {memory.payload.agent_id && (
                    <div>
                      <span className="text-xs text-muted-foreground">Agent ID</span>
                      <div className="mt-1">
                        <Badge variant="outline" className="font-mono text-xs">
                          {memory.payload.agent_id}
                        </Badge>
                      </div>
                    </div>
                  )}
                  {memory.payload.run_id && (
                    <div>
                      <span className="text-xs text-muted-foreground">Run ID</span>
                      <div className="mt-1">
                        <Badge variant="outline" className="font-mono text-xs">
                          {memory.payload.run_id}
                        </Badge>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Additional Metadata */}
            {memory.metadata && Object.keys(memory.metadata).length > 0 && (
              <div className="space-y-3">
                <h4 className="text-sm font-medium">Additional Metadata</h4>
                <div className="p-3 bg-muted rounded-md">
                  <pre className="text-xs whitespace-pre-wrap">
                    {JSON.stringify(memory.metadata, null, 2)}
                  </pre>
                </div>
              </div>
            )}

            {/* Raw Payload */}
            {memory.payload && (
              <div className="space-y-3">
                <h4 className="text-sm font-medium">Raw Payload</h4>
                <div className="p-3 bg-muted rounded-md">
                  <pre className="text-xs whitespace-pre-wrap">
                    {JSON.stringify(memory.payload, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
