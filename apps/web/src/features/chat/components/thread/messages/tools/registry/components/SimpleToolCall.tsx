import React, { useState } from "react";
import { ToolComponentProps } from "../../types";
import { Card } from "@/components/ui/card";
import { ChevronDown, ChevronRight, Loader2, CheckCircle, XCircle, MessageSquare } from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { getToolDisplayName } from "../../utils";
import { ToolArgumentsTable, ToolResultDisplay } from "../shared";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";

/**
 * Detect if the tool result is from a tool approval rejection
 */
function isRejectedToolCall(toolResult?: any): boolean {
  if (!toolResult?.content) return false;
  const content = String(toolResult.content);
  return content.includes("**Tool Call Rejected**") ||
         content.includes("decided not to proceed with this action");
}

/**
 * Detect if the tool result is from human feedback/response
 */
function isHumanFeedback(toolResult?: any): boolean {
  if (!toolResult?.content) return false;
  const content = String(toolResult.content);
  return content.includes("**Human Feedback on") ||
         content.includes("reviewed your tool call and provided this feedback");
}

export function SimpleToolCall({
  toolCall,
  toolResult,
  state,
  streaming
}: ToolComponentProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toolDisplayName = getToolDisplayName(toolCall);
  const hasArgs = toolCall.args && Object.keys(toolCall.args).length > 0;
  const hasExpandableContent = hasArgs || (state === 'completed' && toolResult);

  // Detect approval states
  const isRejected = state === 'completed' && isRejectedToolCall(toolResult);
  const isFeedback = state === 'completed' && isHumanFeedback(toolResult);

  const getStateText = () => {
    if (state === 'completed') {
      if (isRejected) {
        return `Tool Rejected: ${toolDisplayName}`;
      }
      if (isFeedback) {
        return `Human Feedback: ${toolDisplayName}`;
      }
      return `Tool Complete: ${toolDisplayName}`;
    }
    return `Agent is using the following tool: ${toolDisplayName}`;
  };

  const getStateBadge = () => {
    if (state === 'completed') {
      if (isRejected) {
        return (
          <MinimalistBadge
            icon={XCircle}
            tooltip="Tool call rejected by user"
          />
        );
      }
      if (isFeedback) {
        return (
          <MinimalistBadge
            icon={MessageSquare}
            tooltip="User provided feedback"
          />
        );
      }
      return (
        <MinimalistBadge
          icon={CheckCircle}
          tooltip="Tool execution completed"
        />
      );
    }

    return (
      <MinimalistBadge
        icon={Loader2}
        tooltip="Tool executing"
        className="animate-spin-slow"
      />
    );
  };

  const toggleExpanded = () => {
    if (hasExpandableContent) {
      setIsExpanded(!isExpanded);
    }
  };

  return (
    <Card className={cn(
      // Subtle, less invasive container – closer to Claude's style
      "overflow-hidden relative group transition-colors duration-200 ease-out py-0 gap-0 w-full rounded-md shadow-none border border-border/70",
      hasExpandableContent && "hover:bg-muted/30 hover:border-border"
    )}>
      {/* Main Content Row */}
      <div 
        className={cn(
          "px-3.5 py-2.5 flex items-center justify-between gap-3 w-full min-h-0",
          hasExpandableContent && "cursor-pointer"
        )}
        onClick={hasExpandableContent ? toggleExpanded : undefined}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {/* State Badge */}
          {getStateBadge()}
          
          {/* Title */}
          <div className="text-sm text-foreground min-w-0 flex-1">
            <span className="truncate">
              {getStateText()}
            </span>
          </div>
          
          {/* Expand/Collapse Icon */}
          {hasExpandableContent && (
            <div className="flex-shrink-0">
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </div>
          )}
        </div>
      </div>

      {/* Expandable Content */}
      {hasExpandableContent && isExpanded && (
        <div className="px-3.5 pb-2.5 border-t border-border/70 bg-background/40">
          <div className="pt-3 min-w-0">
            <div className={cn("max-h-56 pr-1", ...getScrollbarClasses('y'))}>
              <div className="space-y-3 min-w-0">
                {/* Show arguments if available */}
                {hasArgs && (
                  <div className="min-w-0">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5">Arguments</div>
                    <div className="min-w-0 break-anywhere">
                      <ToolArgumentsTable args={toolCall.args} />
                    </div>
                  </div>
                )}
                
                {/* Show result if completed */}
                {state === 'completed' && toolResult && (
                  <div className="min-w-0 break-anywhere">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5">Result</div>
                    <ToolResultDisplay toolResult={toolResult} />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}


    </Card>
  );
} 