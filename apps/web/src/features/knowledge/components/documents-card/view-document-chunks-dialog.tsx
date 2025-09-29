"use client";

import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
      <DialogContent className={cn("!max-w-4xl !w-[70vw] max-h-[85vh] flex flex-col", ...getScrollbarClasses('y'))}>
        <DialogHeader className="flex-shrink-0">
          <DialogTitle>Document Chunks</DialogTitle>
          <p className="text-sm text-muted-foreground">
            {chunks.length} chunk{chunks.length !== 1 ? 's' : ''} from "{documentTitle}"
          </p>
        </DialogHeader>

        <div className="flex-1 min-h-0">
          {chunks.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-center text-muted-foreground">
                  No chunks available for this document.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className={cn(
              "space-y-4 overflow-y-auto pr-2",
              ...getScrollbarClasses('y')
            )}>
              {chunks.map((chunk, index) => (
                <Card key={chunk.id} className="relative">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">
                      Chunk {index + 1}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <div className={cn(
                      "max-h-[300px] overflow-y-auto rounded-lg border bg-muted/10 p-4",
                      ...getScrollbarClasses('y')
                    )}>
                      <MarkdownText className="text-sm">
                        {chunk.content || chunk.content_preview}
                      </MarkdownText>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
} 