import React from "react";
import { ToolComponentProps } from "../../types";
import { ToolCalls, ToolResult } from "../../../tool-calls";

export function DefaultToolCall({ 
  toolCall, 
  toolResult, 
  state 
}: ToolComponentProps) {
  // For completed state, show the tool result
  if (state === 'completed' && toolResult) {
    return <ToolResult message={toolResult} />;
  }

  // For loading/error states, show the tool call
  return <ToolCalls toolCalls={[toolCall]} />;
} 