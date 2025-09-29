import React from "react";
import { ToolMessage } from "@langchain/langgraph-sdk";
import { getToolComponent, isSilentTool } from "./registry";
import { useQueryState, parseAsBoolean } from "nuqs";
import { ToolComponentProps } from "./types";

interface ToolCallResolverProps {
  toolCall: NonNullable<import("@langchain/langgraph-sdk").AIMessage["tool_calls"]>[0];
  toolResult?: ToolMessage;
  state: 'loading' | 'completed' | 'error';
  streaming?: boolean;
  graphId?: string;
  onRetry?: () => void;
}

export function ToolCallResolver({ 
  toolCall, 
  toolResult, 
  state, 
  streaming,
  graphId,
  onRetry 
}: ToolCallResolverProps) {
  const [hideToolCalls] = useQueryState("hideToolCalls", parseAsBoolean.withDefault(false));
  
  // Use the provided graphId, fallback to "*" for global registry matching
  const effectiveGraphId = graphId || "*";
  
  // Check if this tool should be silent
  if (isSilentTool(toolCall.name, effectiveGraphId)) {
    return null;
  }
  
  // Get the appropriate component
  const ToolComponent = getToolComponent(toolCall.name, effectiveGraphId, hideToolCalls);
  
  if (!ToolComponent) {
    return null; // Hidden by toggle or silent
  }
  
  const componentProps: ToolComponentProps = {
    toolCall,
    toolResult,
    state,
    streaming,
    graphId: effectiveGraphId,
    onRetry
  };
  
  return <ToolComponent {...componentProps} />;
} 