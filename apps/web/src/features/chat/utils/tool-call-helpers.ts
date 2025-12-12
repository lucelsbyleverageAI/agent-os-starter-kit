/**
 * Helper functions for handling tool calls and cancellation.
 *
 * Used primarily when a user cancels a thread while tool calls are in progress.
 * We inject synthetic ToolMessages to mark them as cancelled, which allows
 * the UI to display them properly instead of showing loading spinners.
 */

import type { Message } from "@langchain/langgraph-sdk";

interface PendingToolCall {
  toolCallId: string;
  toolName: string;
}

/**
 * Find all tool calls that don't have corresponding ToolMessage responses.
 *
 * Scans through messages to find AIMessage tool_calls and checks which ones
 * are missing their ToolMessage response.
 */
export function findPendingToolCalls(messages: Message[]): PendingToolCall[] {
  // Collect all tool call IDs and their names from AIMessages
  const toolCallIds = new Map<string, string>();

  for (const msg of messages) {
    if (msg.type === "ai") {
      const aiMsg = msg as any;
      if (aiMsg.tool_calls && Array.isArray(aiMsg.tool_calls)) {
        for (const tc of aiMsg.tool_calls) {
          if (tc.id && tc.name) {
            toolCallIds.set(tc.id, tc.name);
          }
        }
      }
    }
  }

  // Remove IDs that have ToolMessage responses
  for (const msg of messages) {
    if (msg.type === "tool") {
      const toolMsg = msg as any;
      if (toolMsg.tool_call_id) {
        toolCallIds.delete(toolMsg.tool_call_id);
      }
    }
  }

  // Return remaining pending tool calls
  return Array.from(toolCallIds.entries()).map(([id, name]) => ({
    toolCallId: id,
    toolName: name,
  }));
}

/**
 * Create a synthetic ToolMessage for a cancelled tool call.
 *
 * The content is JSON with a status field that the frontend's
 * DefaultToolCall component detects to show the cancelled UI.
 */
export function createCancelledToolMessage(
  toolCallId: string,
  toolName: string
): Message {
  return {
    type: "tool",
    tool_call_id: toolCallId,
    name: toolName,
    content: JSON.stringify({
      status: "cancelled",
      message: "Tool execution was cancelled before completion.",
    }),
  } as Message;
}
