import React, { useState, useCallback, useEffect, useRef } from "react";
import { ToolComponentProps } from "../../types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Bot,
  CheckCircle,
  Loader2,
  AlertCircle,
  ChevronRight,
  ChevronDown,
  XOctagon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useSubAgentPreviewOptional } from "@/features/chat/context/subagent-preview-context";

interface TaskArgs {
  description?: string;
  subagent_type?: string;
}

/**
 * Detect if the tool result is from a cancelled tool call.
 * This happens when a thread is cancelled during tool execution.
 * The frontend injects synthetic ToolMessages with {"status": "cancelled", ...}
 */
function isCancelledToolCall(toolResult?: any): boolean {
  if (!toolResult?.content) return false;
  try {
    let content = toolResult.content;

    // Handle array of content blocks (Claude/Anthropic format)
    // Format: [{ text: "...", type: "text", index: 0 }]
    if (Array.isArray(content)) {
      const textBlock = content.find(
        (block: any) => typeof block === "object" && block !== null && "text" in block
      );
      if (textBlock) {
        content = textBlock.text;
      } else {
        content = JSON.stringify(content);
      }
    }

    if (typeof content !== 'string') {
      content = JSON.stringify(content);
    }

    const parsed = JSON.parse(content);
    return parsed?.status === 'cancelled';
  } catch {
    return false;
  }
}

export function TaskTool({
  toolCall,
  toolResult,
  state,
  streaming,
  onRetry
}: ToolComponentProps) {
  const subagentPreview = useSubAgentPreviewOptional();
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false);

  // Extract args
  const args = toolCall.args as TaskArgs;
  const taskDescription = args?.description || "Delegated task";
  const subagentType = args?.subagent_type || "sub-agent";

  // Check if description is long enough to need expansion (rough heuristic)
  const isDescriptionLong = taskDescription.length > 80;

  // Get response content
  let responseContent: string | null = null;
  if (state === "completed" && toolResult?.content) {
    const content = toolResult.content;
    if (typeof content === "string") {
      responseContent = content;
    } else if (Array.isArray(content)) {
      // Handle array of content blocks (Claude/Anthropic format)
      // Format: [{ text: "...", type: "text", index: 0 }]
      const textParts: string[] = [];
      for (const block of content) {
        if (
          typeof block === "object" &&
          block !== null &&
          "text" in block &&
          typeof (block as { text: unknown }).text === "string"
        ) {
          textParts.push((block as { text: string }).text);
        }
      }
      responseContent = textParts.length > 0
        ? textParts.join("\n")
        : JSON.stringify(content, null, 2);
    } else {
      // Fallback for other object types
      responseContent = JSON.stringify(content, null, 2);
    }
  }

  // Handler to open preview
  const handleOpenPreview = useCallback(() => {
    if (responseContent && subagentPreview) {
      subagentPreview.openPreview({
        subagentType,
        taskDescription,
        response: responseContent,
        toolCallId: toolCall.id || '',
      });
    }
  }, [responseContent, subagentPreview, subagentType, taskDescription, toolCall.id]);

  // Track if we observed a loading/streaming state (meaning tool ran during this session)
  const wasLoadingRef = useRef(false);
  // Track if we've already auto-opened the preview for this tool call
  const hasAutoOpenedRef = useRef(false);

  // Track if we ever saw a loading state
  useEffect(() => {
    if (state === "loading" || streaming) {
      wasLoadingRef.current = true;
    }
  }, [state, streaming]);

  // Auto-open preview when tool completes successfully (only if we saw loading first)
  useEffect(() => {
    if (state === "completed" && responseContent && subagentPreview &&
        !hasAutoOpenedRef.current && wasLoadingRef.current) {
      hasAutoOpenedRef.current = true;
      handleOpenPreview();
    }
  }, [state, responseContent, subagentPreview, handleOpenPreview]);

  // Toggle description expansion
  const toggleDescription = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setIsDescriptionExpanded(prev => !prev);
  }, []);

  // Loading state
  if (state === "loading" || streaming) {
    return (
      <Card className="w-full p-4">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 h-8 w-8 rounded-full bg-muted flex items-center justify-center mt-0.5">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-foreground">
                Delegating to
              </span>
              <Badge variant="secondary" className="text-xs">
                {subagentType}
              </Badge>
            </div>
            <div className="mt-0.5">
              {isDescriptionLong ? (
                <button
                  onClick={toggleDescription}
                  className="flex items-start gap-1 text-left w-full group"
                >
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 text-muted-foreground flex-shrink-0 mt-0.5 transition-transform",
                      !isDescriptionExpanded && "-rotate-90"
                    )}
                  />
                  <p className={cn(
                    "text-sm text-muted-foreground",
                    !isDescriptionExpanded && "line-clamp-1"
                  )}>
                    {taskDescription}
                  </p>
                </button>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {taskDescription}
                </p>
              )}
            </div>
          </div>
        </div>
      </Card>
    );
  }

  // Cancelled state (error with no result)
  if (state === "error" && !toolResult) {
    return (
      <Card className="w-full p-4">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 h-8 w-8 rounded-full bg-orange-100 flex items-center justify-center mt-0.5">
            <XOctagon className="h-4 w-4 text-orange-500" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-foreground">
                Task cancelled
              </span>
              <Badge variant="secondary" className="text-xs">
                {subagentType}
              </Badge>
            </div>
            <div className="mt-0.5">
              {isDescriptionLong ? (
                <button
                  onClick={toggleDescription}
                  className="flex items-start gap-1 text-left w-full group"
                >
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 text-muted-foreground flex-shrink-0 mt-0.5 transition-transform",
                      !isDescriptionExpanded && "-rotate-90"
                    )}
                  />
                  <p className={cn(
                    "text-sm text-muted-foreground",
                    !isDescriptionExpanded && "line-clamp-1"
                  )}>
                    {taskDescription}
                  </p>
                </button>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {taskDescription}
                </p>
              )}
            </div>
          </div>
        </div>
      </Card>
    );
  }

  // Error state (actual failure with result)
  if (state === "error") {
    return (
      <Card className="w-full p-4">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 h-8 w-8 rounded-full bg-destructive/10 flex items-center justify-center mt-0.5">
            <AlertCircle className="h-4 w-4 text-destructive" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-foreground">
                Task failed
              </span>
              <Badge variant="secondary" className="text-xs">
                {subagentType}
              </Badge>
            </div>
            <div className="mt-0.5">
              {isDescriptionLong ? (
                <button
                  onClick={toggleDescription}
                  className="flex items-start gap-1 text-left w-full group"
                >
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 text-muted-foreground flex-shrink-0 mt-0.5 transition-transform",
                      !isDescriptionExpanded && "-rotate-90"
                    )}
                  />
                  <p className={cn(
                    "text-sm text-muted-foreground",
                    !isDescriptionExpanded && "line-clamp-1"
                  )}>
                    {taskDescription}
                  </p>
                </button>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {taskDescription}
                </p>
              )}
            </div>
          </div>
          {onRetry && (
            <Button onClick={onRetry} variant="outline" size="sm" className="flex-shrink-0 mt-0.5">
              Retry
            </Button>
          )}
        </div>
      </Card>
    );
  }

  // Cancelled state (detected from content - synthetic cancelled ToolMessage)
  // This handles the case where frontend injects {"status":"cancelled",...} on cancellation
  if (state === "completed" && isCancelledToolCall(toolResult)) {
    return (
      <Card className="w-full p-4">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 h-8 w-8 rounded-full bg-orange-100 flex items-center justify-center mt-0.5">
            <XOctagon className="h-4 w-4 text-orange-500" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-foreground">
                Task cancelled
              </span>
              <Badge variant="secondary" className="text-xs">
                {subagentType}
              </Badge>
            </div>
            <div className="mt-0.5">
              {isDescriptionLong ? (
                <button
                  onClick={toggleDescription}
                  className="flex items-start gap-1 text-left w-full group"
                >
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 text-muted-foreground flex-shrink-0 mt-0.5 transition-transform",
                      !isDescriptionExpanded && "-rotate-90"
                    )}
                  />
                  <p className={cn(
                    "text-sm text-muted-foreground",
                    !isDescriptionExpanded && "line-clamp-1"
                  )}>
                    {taskDescription}
                  </p>
                </button>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {taskDescription}
                </p>
              )}
            </div>
          </div>
        </div>
      </Card>
    );
  }

  // Completed state (actual success)
  return (
    <Card
      className="w-full overflow-hidden py-0 gap-0 cursor-pointer hover:bg-accent/50 transition-colors"
      onClick={handleOpenPreview}
    >
      <div className="py-4 px-4">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className="flex-shrink-0 h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center mt-0.5">
            <Bot className="h-4 w-4 text-primary" />
          </div>

          {/* Task Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-3.5 w-3.5 text-green-500 flex-shrink-0" />
              <span className="text-sm font-medium text-foreground">
                Task completed
              </span>
              <Badge variant="secondary" className="text-xs">
                {subagentType}
              </Badge>
            </div>
            <div className="mt-0.5">
              {isDescriptionLong ? (
                <button
                  onClick={toggleDescription}
                  className="flex items-start gap-1 text-left w-full group"
                >
                  <ChevronDown
                    className={cn(
                      "h-3.5 w-3.5 text-muted-foreground flex-shrink-0 mt-0.5 transition-transform",
                      !isDescriptionExpanded && "-rotate-90"
                    )}
                  />
                  <p className={cn(
                    "text-sm text-muted-foreground",
                    !isDescriptionExpanded && "line-clamp-1"
                  )}>
                    {taskDescription}
                  </p>
                </button>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {taskDescription}
                </p>
              )}
            </div>
          </div>

          {/* View Button */}
          <Button
            variant="ghost"
            size="sm"
            className="flex-shrink-0 h-8 text-xs mt-0.5"
            onClick={(e) => {
              e.stopPropagation();
              handleOpenPreview();
            }}
          >
            View
            <ChevronRight className="h-3.5 w-3.5 ml-1" />
          </Button>
        </div>
      </div>
    </Card>
  );
}
