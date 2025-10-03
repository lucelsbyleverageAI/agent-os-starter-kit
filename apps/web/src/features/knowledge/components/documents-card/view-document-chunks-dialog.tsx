"use client";

import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { MarkdownText } from "@/components/ui/markdown-text";

interface ChunkData {
  id: string;
  content_preview: string;
  content: string;
  content_length: number;
  metadata: Record<string, any>;
  embedding?: any;
}

interface ViewDocumentChunksDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chunks: ChunkData[];
  documentTitle: string;
}

export function ViewDocumentChunksDialog({
  open,
  onOpenChange,
  chunks,
  documentTitle,
}: ViewDocumentChunksDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn("!max-w-4xl !w-[70vw] max-h-[85vh] flex flex-col gap-0", ...getScrollbarClasses('y'))}>
        <DialogHeader className="flex-shrink-0 pb-4">
          <DialogTitle>Document Chunks</DialogTitle>
          <p className="text-sm text-muted-foreground mt-1">
            {chunks.length} chunk{chunks.length !== 1 ? 's' : ''} from "{documentTitle}"
          </p>
        </DialogHeader>

        <div className="flex-1 min-h-0">
          {chunks.length === 0 ? (
            <div className="rounded-md border border-border/30 bg-muted/5 p-6">
              <p className="text-center text-muted-foreground">
                No chunks available for this document.
              </p>
            </div>
          ) : (
            <div className={cn(
              "h-full space-y-3 overflow-y-auto pr-2",
              ...getScrollbarClasses('y')
            )}>
              {chunks.map((chunk, index) => (
                <div 
                  key={chunk.id} 
                  className="rounded-md border border-border/30 bg-muted/5 p-4"
                >
                  <div className="text-xs font-medium text-muted-foreground mb-3">
                    Chunk {index + 1}
                  </div>
                  <div className={cn(
                    "max-h-[300px] overflow-y-auto",
                    ...getScrollbarClasses('y')
                  )}>
                    <MarkdownText className="text-sm">
                      {chunk.content || chunk.content_preview}
                    </MarkdownText>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
} 