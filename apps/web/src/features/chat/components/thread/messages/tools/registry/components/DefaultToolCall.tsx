import React from "react";
import { ToolComponentProps } from "../../types";
import { ToolCalls, ToolResult } from "../../../tool-calls";
import { XCircle, MessageSquare, CheckCircle } from "lucide-react";

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
 * Custom ToolResult component that shows approval status icons
 */
function ApprovalAwareToolResult({
  message,
  isRejected,
  isFeedback
}: {
  message: any;
  isRejected: boolean;
  isFeedback: boolean;
}) {
  const Icon = isRejected ? XCircle : isFeedback ? MessageSquare : CheckCircle;
  const iconColor = isRejected
    ? "text-red-500"
    : isFeedback
    ? "text-blue-500"
    : "text-green-500";
  const borderColor = isRejected
    ? "border-red-200"
    : isFeedback
    ? "border-blue-200"
    : "border-gray-200";
  const bgColor = isRejected
    ? "bg-red-50"
    : isFeedback
    ? "bg-blue-50"
    : "bg-gray-50";

  return (
    <div className={`w-full overflow-hidden rounded-lg border ${borderColor}`}>
      <div className={`border-b ${borderColor} ${bgColor} px-4 py-2`}>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Icon className={`h-4 w-4 ${iconColor}`} />
            {message.name ? (
              <h3 className="font-medium text-gray-900">
                {isRejected ? "Rejected: " : isFeedback ? "Feedback: " : "Tool Result: "}
                <code className="rounded bg-gray-100 px-2 py-1">
                  {message.name}
                </code>
              </h3>
            ) : (
              <h3 className="font-medium text-gray-900">
                {isRejected ? "Tool Call Rejected" : isFeedback ? "Human Feedback" : "Tool Result"}
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
          {String(message.content)}
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

    // Use custom component if it's a rejection or feedback response
    if (rejected || feedback) {
      return (
        <ApprovalAwareToolResult
          message={toolResult}
          isRejected={rejected}
          isFeedback={feedback}
        />
      );
    }

    // Otherwise use the standard ToolResult component
    return <ToolResult message={toolResult} />;
  }

  // For loading/error states, show the tool call
  return <ToolCalls toolCalls={[toolCall]} />;
} 