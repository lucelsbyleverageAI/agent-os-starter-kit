import React from "react";
import { ToolComponentProps } from "../../types";
import { ToolCalls, ToolResult } from "../../../tool-calls";
import { XCircle, MessageSquare, CheckCircle, XOctagon } from "lucide-react";

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

/**
 * Detect if the tool result is from a cancelled tool call
 * This happens when a thread is cancelled during tool execution.
 * The frontend/backend inserts synthetic ToolMessages with {"status": "cancelled", ...}
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

/**
 * Custom ToolResult component that shows approval/status icons
 * Supports: rejected, feedback, cancelled, and normal completed states
 */
function ApprovalAwareToolResult({
  message,
  isRejected,
  isFeedback,
  isCancelled
}: {
  message: any;
  isRejected: boolean;
  isFeedback: boolean;
  isCancelled: boolean;
}) {
  // Determine icon based on state (priority: cancelled > rejected > feedback > success)
  const Icon = isCancelled
    ? XOctagon
    : isRejected
    ? XCircle
    : isFeedback
    ? MessageSquare
    : CheckCircle;

  const iconColor = isCancelled
    ? "text-orange-500"
    : isRejected
    ? "text-red-500"
    : isFeedback
    ? "text-blue-500"
    : "text-green-500";

  const borderColor = isCancelled
    ? "border-orange-200"
    : isRejected
    ? "border-red-200"
    : isFeedback
    ? "border-blue-200"
    : "border-gray-200";

  const bgColor = isCancelled
    ? "bg-orange-50"
    : isRejected
    ? "bg-red-50"
    : isFeedback
    ? "bg-blue-50"
    : "bg-gray-50";

  const label = isCancelled
    ? "Cancelled: "
    : isRejected
    ? "Rejected: "
    : isFeedback
    ? "Feedback: "
    : "Tool Result: ";

  const labelNoName = isCancelled
    ? "Tool Call Cancelled"
    : isRejected
    ? "Tool Call Rejected"
    : isFeedback
    ? "Human Feedback"
    : "Tool Result";

  // For cancelled, show a user-friendly message instead of raw JSON
  const displayContent = isCancelled
    ? "Tool execution was cancelled before completion."
    : String(message.content);

  return (
    <div className={`w-full overflow-hidden rounded-lg border ${borderColor}`}>
      <div className={`border-b ${borderColor} ${bgColor} px-4 py-2`}>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Icon className={`h-4 w-4 ${iconColor}`} />
            {message.name ? (
              <h3 className="font-medium text-gray-900">
                {label}
                <code className="rounded bg-gray-100 px-2 py-1">
                  {message.name}
                </code>
              </h3>
            ) : (
              <h3 className="font-medium text-gray-900">
                {labelNoName}
              </h3>
            )}
          </div>
          {message.tool_call_id && (
            <code className="rounded bg-gray-100 px-2 py-1 text-sm">
              {message.tool_call_id}
            </code>
          )}
        </div>
      </div>
      <div className="bg-gray-100 p-3">
        <code className="block overflow-x-auto text-sm whitespace-pre-wrap">
          {displayContent}
        </code>
      </div>
    </div>
  );
}

export function DefaultToolCall({
  toolCall,
  toolResult,
  state
}: ToolComponentProps) {
  // For completed state, show the tool result with approval-aware styling
  if (state === 'completed' && toolResult) {
    const rejected = isRejectedToolCall(toolResult);
    const feedback = isHumanFeedback(toolResult);
    const cancelled = isCancelledToolCall(toolResult);

    // Use custom component for special states (rejection, feedback, cancelled)
    if (rejected || feedback || cancelled) {
      return (
        <ApprovalAwareToolResult
          message={toolResult}
          isRejected={rejected}
          isFeedback={feedback}
          isCancelled={cancelled}
        />
      );
    }

    // Otherwise use the standard ToolResult component
    return <ToolResult message={toolResult} />;
  }

  // For error state with no result - this is an orphaned/cancelled tool call
  // This happens when a thread is cancelled mid-execution and no ToolMessage was received
  if (state === 'error' && !toolResult) {
    // Create a synthetic message object for the cancelled UI
    const syntheticMessage = {
      name: toolCall.name,
      tool_call_id: toolCall.id,
      content: "Tool execution was cancelled before completion."
    };
    return (
      <ApprovalAwareToolResult
        message={syntheticMessage}
        isRejected={false}
        isFeedback={false}
        isCancelled={true}
      />
    );
  }

  // For loading states, show the tool call
  return <ToolCalls toolCalls={[toolCall]} />;
} 