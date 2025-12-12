import { AIMessage, ToolMessage, Message } from "@langchain/langgraph-sdk";
import { ToolCallWithResult } from "./types";

/**
 * Match tool calls with their corresponding tool results
 * @param toolCalls - Array of tool calls from an AI message
 * @param messages - All messages in the thread
 * @param isLoading - Whether the thread is currently loading
 * @returns Array of tool calls with their matched results and states
 */
export function matchToolCallsWithResults(
  toolCalls: NonNullable<AIMessage["tool_calls"]>,
  messages: Message[],
  isLoading: boolean
): ToolCallWithResult[] {
  // Filter out incomplete/empty tool calls that might appear during streaming
  const validToolCalls = toolCalls.filter(toolCall =>
    toolCall.name && toolCall.name.length > 0
  );

  // Find all tool results in the thread
  const toolResults = messages.filter(
    (msg): msg is ToolMessage => msg.type === "tool"
  );

  return validToolCalls.map((toolCall, index) => {
    // Try to find corresponding tool result
    const toolResult = toolResults.find(
      (result) => result.tool_call_id === toolCall.id
    );

    // Analyze tool call completeness
    const hasArgs = toolCall.args !== undefined && toolCall.args !== null;
    const hasName = toolCall.name && toolCall.name.length > 0;
    const argsCount = hasArgs ? Object.keys(toolCall.args).length : 0;

    // Determine state based on results and completeness
    let state: 'loading' | 'completed' | 'error';
    let streaming = false;

    if (toolResult) {
      // We have a result - tool call is complete
      state = "completed";
    } else if (isLoading) {
      // Still loading and no result yet
      if (hasName && hasArgs && argsCount > 0) {
        // Tool call looks complete, probably executing
        state = "loading";
        streaming = true;
      } else {
        // Tool call still forming/streaming
        state = "loading";
        streaming = true;
      }
    } else {
      // Not loading anymore but no result - something went wrong
      state = "error";
    }

    return {
      toolCall,
      toolResult: toolResult || undefined,
      state,
      streaming
    };
  });
}

/**
 * Check if a tool call has arguments
 */
export function hasToolCallArgs(toolCall: NonNullable<AIMessage["tool_calls"]>[0]): boolean {
  return toolCall.args && Object.keys(toolCall.args).length > 0;
}

/**
 * Get a display name for a tool call
 */
export function getToolDisplayName(toolCall: NonNullable<AIMessage["tool_calls"]>[0]): string {
  // Convert snake_case to Title Case
  return toolCall.name
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Check if tool calls are still streaming (being built)
 */
export function areToolCallsStreaming(
  toolCalls: NonNullable<AIMessage["tool_calls"]>,
  isLoading: boolean
): boolean {
  if (!isLoading) return false;
  
  // If any tool call has incomplete args, consider it streaming
  return toolCalls.some(tc => !tc.args || Object.keys(tc.args).length === 0);
}

/**
 * Extract error message from tool result if it represents an error
 */
export function getToolErrorMessage(toolResult: ToolMessage): string | null {
  try {
    const content = typeof toolResult.content === 'string' 
      ? JSON.parse(toolResult.content)
      : toolResult.content;
    
    if (content?.error) {
      return content.error;
    }
    
    if (content?.message && content?.type === 'error') {
      return content.message;
    }
    
    return null;
  } catch {
    // If content is not JSON or doesn't match error patterns, not an error
    return null;
  }
} 