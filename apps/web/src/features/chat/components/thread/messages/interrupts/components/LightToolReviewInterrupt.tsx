import React, { useState } from "react";
import { InterruptComponentProps } from "../index";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CheckCircle, XCircle, Info, ChevronDown, ChevronRight } from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { prettifyText } from "@/features/chat/utils/interrupt-utils";
import { HumanResponse } from "../../interrupt-types";
import { MarkdownText } from "@/components/ui/markdown-text";
import { cn } from "@/lib/utils";

export function LightToolReviewInterrupt({ 
  interrupt, 
  onSubmit, 
  streaming = false, 
  loading = false 
}: InterruptComponentProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const actionsDisabled = loading || streaming;
  
  // Extract tool name from action (remove 'tool_call_review_' prefix)
  const toolName = interrupt.action_request.action.replace('tool_call_review_', '');
  const readableToolName = prettifyText(toolName);

  const handleAccept = async () => {
    const response: HumanResponse = {
      type: "accept",
      args: null
    };
    await onSubmit?.(response);
  };

  const handleDeny = async () => {
    const response: HumanResponse = {
      type: "ignore", 
      args: null
    };
    await onSubmit?.(response);
  };

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <Card className={cn(
      "overflow-hidden relative group transition-all duration-300 ease-out py-0 gap-0",
      "hover:border-primary hover:border-2 hover:shadow-lg hover:shadow-primary/10 vibrate-on-hover"
    )}>
      {/* Main Content Row */}
      <div 
        className="px-4 py-3 cursor-pointer flex items-center justify-between gap-3 w-full min-h-0"
        onClick={toggleExpanded}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {/* Tool Badge */}
          <MinimalistBadge
            icon={Info}
            tooltip="Tool Execution Request"
          />
          
          {/* Title */}
          <div className="text-sm font-medium text-foreground min-w-0 flex-1">
            <span className="truncate">
              Agent wants to use the following tool: <span className="font-semibold">{readableToolName}</span>
            </span>
          </div>
          
          {/* Expand/Collapse Icon */}
          {interrupt.description && (
            <div className="flex-shrink-0">
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
          <Button
            variant="default"
            size="sm"
            onClick={handleAccept}
            disabled={actionsDisabled}
          >
            <CheckCircle className="h-4 w-4 mr-1" />
            Accept
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDeny}
            disabled={actionsDisabled}
          >
            <XCircle className="h-4 w-4 mr-1" />
            Deny
          </Button>
        </div>
      </div>

      {/* Expandable Description */}
      {interrupt.description && isExpanded && (
        <div className="px-4 pb-3 border-t border-border">
          <div className="pt-3">
            <MarkdownText className="text-sm text-muted-foreground leading-relaxed">
              {interrupt.description}
            </MarkdownText>
          </div>
        </div>
      )}

      {/* Loading state overlay */}
      {streaming && (
        <div className="px-4 pb-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <div className="h-1 w-1 animate-pulse rounded-full bg-primary"></div>
            Processing...
          </div>
        </div>
      )}
    </Card>
  );
} 