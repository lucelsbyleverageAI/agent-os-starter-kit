import { AIMessage, ToolMessage } from "@langchain/langgraph-sdk";

export interface ToolComponentProps {
  toolCall: NonNullable<AIMessage["tool_calls"]>[0];
  toolResult?: ToolMessage;
  state: 'loading' | 'completed' | 'error';
  streaming?: boolean;
  graphId: string;
  onRetry?: () => void;
}

export type ToolComponent = React.ComponentType<ToolComponentProps>;

export interface ToolRegistryEntry {
  component: ToolComponent;
  graphIds?: string[];  // If specified, only show for these graphs
  silent?: boolean;     // If true, never render regardless of toggle
}

export type ToolRegistry = Record<string, ToolRegistryEntry>;

export interface ToolCallWithResult {
  toolCall: NonNullable<AIMessage["tool_calls"]>[0];
  toolResult?: ToolMessage;
  state: 'loading' | 'completed' | 'error';
  streaming?: boolean;
} 