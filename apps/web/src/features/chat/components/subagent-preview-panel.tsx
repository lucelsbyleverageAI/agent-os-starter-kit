"use client";

import React, { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { X, Copy, Check, Bot } from "lucide-react";
import { MarkdownText } from "@/components/ui/markdown-text";
import { cn } from "@/lib/utils";
import { scrollbarClasses } from "@/lib/scrollbar-styles";
import { useSubAgentPreview } from "../context/subagent-preview-context";
import { Badge } from "@/components/ui/badge";

export function SubAgentPreviewPanel() {
  const { preview, closePreview } = useSubAgentPreview();
  const [copied, setCopied] = useState(false);

  // Copy handler for markdown content
  const handleCopy = useCallback(async () => {
    if (!preview?.response) return;

    try {
      await navigator.clipboard.writeText(preview.response);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Copy failed silently
    }
  }, [preview?.response]);

  if (!preview) return null;

  return (
    <div className="flex flex-col h-full border-l bg-muted/30">
      {/* Header */}
      <div className="p-4 pb-3 border-b flex-shrink-0 bg-muted/50">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Bot className="h-4 w-4 text-muted-foreground flex-shrink-0" />
              <Badge variant="secondary" className="text-xs">
                {preview.subagentType}
              </Badge>
            </div>
            <h2 className="font-semibold text-foreground text-sm line-clamp-2">
              {preview.taskDescription}
            </h2>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopy}
            >
              {copied ? (
                <>
                  <Check className="h-4 w-4 mr-2" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="h-4 w-4 mr-2" />
                  Copy
                </>
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={closePreview}
              className="h-8 w-8"
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Close preview</span>
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <ScrollArea className={cn("flex-1 min-h-0", scrollbarClasses.y)}>
        <div className="p-4">
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <MarkdownText>{preview.response}</MarkdownText>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
