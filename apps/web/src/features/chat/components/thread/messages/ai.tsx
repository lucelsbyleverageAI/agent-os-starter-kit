import { useStreamContext } from "@/features/chat/providers/Stream";
import { AIMessage, Checkpoint, Message } from "@langchain/langgraph-sdk";
import { getContentString } from "@/features/chat/utils/content-string";
import { BranchSwitcher, CommandBar } from "./shared";
import { MarkdownText } from "@/components/ui/markdown-text";
import { LoadExternalComponent } from "@langchain/langgraph-sdk/react-ui";
import { cn } from "@/lib/utils";

import { ToolCallResolver, matchToolCallsWithResults } from "./tools";
import { MessageContentComplex } from "@langchain/core/messages";
import { Fragment } from "react/jsx-runtime";
import { useQueryState, parseAsBoolean } from "nuqs";
import { useMemo } from "react";
import { Interrupt } from "./interrupt";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { Loader2 } from "lucide-react";
import { useAgentsContext } from "@/providers/Agents";
import { isStructuredControlJson } from "@/features/chat/utils/is-structured-json";

function CustomComponent({
  message,
  thread,
}: {
  message: Message;
  thread: ReturnType<typeof useStreamContext>;
}) {
  const { values } = useStreamContext();
  const customComponents = values.ui?.filter(
    (ui: any) => ui.metadata?.message_id === message.id,
  );

  if (!customComponents?.length) return null;
  return (
    <Fragment key={message.id}>
      {customComponents.map((customComponent: any) => (
        <LoadExternalComponent
          key={customComponent.id}
          stream={thread}
          message={customComponent}
          meta={{ ui: customComponent }}
        />
      ))}
    </Fragment>
  );
}

function parseAnthropicStreamedToolCalls(
  content: MessageContentComplex[],
): AIMessage["tool_calls"] {
  // More permissive filtering - detect tool calls even if they don't have complete IDs yet
  const toolCallContents = content.filter((c) => c.type === "tool_use");

  const toolCalls = toolCallContents.map((tc, index) => {
    const toolCall = tc as Record<string, any>;
    return {
      name: toolCall.name || "",
      id: toolCall.id || `streaming-${index}`,
      args: toolCall.input || {},
      type: "tool_call" as const,
    };
  });

  // Filter out tool calls that don't have a name (they're incomplete)
  return toolCalls.filter(tc => tc.name && tc.name.length > 0);
}

/**
 * AssistantMessage component with intelligent action bar placement
 * 
 * KEY STRATEGY: Action bars should only appear when user can meaningfully take action:
 * 
 * ✅ SHOW ACTION BARS:
 * - Messages from completed runs (historical messages) - user can always regenerate
 * - Current run's final message ONLY when run is complete
 * 
 * ❌ HIDE ACTION BARS:
 * - Current run messages while tools are executing/pending
 * - Mid-execution messages even if they have tool calls
 * 
 * This prevents UI gaps during tool execution while preserving regeneration capability
 * for all completed conversation turns.
 */
export function AssistantMessage({
  message,
  isLoading,
  handleRegenerate,
}: {
  message: Message | undefined;
  isLoading: boolean;
  handleRegenerate: (
    parentCheckpoint: Checkpoint | null | undefined,
    optimisticValues?: (prev: { messages?: Message[] }) => {
      messages?: Message[] | undefined;
    },
  ) => void;
}) {
  const content = message?.content ?? [];
  const contentString = getContentString(content);
  const [_hideToolCalls] = useQueryState(
    "hideToolCalls",
    parseAsBoolean.withDefault(false),
  );

  const thread = useStreamContext();
  const meta = message ? thread.getMessagesMetadata(message) : undefined;
  const { agents } = useAgentsContext();
  const [agentId] = useQueryState("agentId");
  
  // Extract graph ID from multiple sources with fallback priority:
  // 1. Message/run metadata (most accurate for each message)
  // 2. Selected assistant mapping (good fallback)
  // 3. Global wildcard as last resort
  const graphId = useMemo(() => {
    // Try to extract from message metadata first
    // Based on stream example, metadata might be accessible through various paths
    let messageGraphId: string | undefined;
    
    // Method 0: Check the current stream context for latest metadata
    // The stream might have metadata from recent updates
    if (thread && typeof thread === 'object') {
      const threadAny = thread as any;
      
      // Check if stream context has current run metadata
      if (threadAny.current?.metadata?.graph_id) {
        messageGraphId = threadAny.current.metadata.graph_id;
      }
      
      // Check if there's latest update metadata
      if (!messageGraphId && threadAny.latestUpdate?.metadata?.graph_id) {
        messageGraphId = threadAny.latestUpdate.metadata.graph_id;
      }
      
      // Check if there's context metadata
      if (!messageGraphId && threadAny.context?.graph_id) {
        messageGraphId = threadAny.context.graph_id;
      }
    }
    
    // Check if thread.values contains metadata for this message
    if (thread.values && message?.id) {
      // Look for metadata that might contain graph_id
      // The stream metadata structure might vary, so we'll check multiple possible locations
      
      // Method 1: Check if values has metadata array or object with graph_id
      if (thread.values && typeof thread.values === 'object') {
        const values = thread.values as any;
        if (values.metadata?.graph_id) {
          messageGraphId = values.metadata.graph_id;
        }
        // Method 2: Check if there's run metadata
        if (!messageGraphId && values.run_metadata?.graph_id) {
          messageGraphId = values.run_metadata.graph_id;
        }
        
        // Method 3: Check if messages array contains metadata objects
        // Based on stream example, metadata comes as second element in messages array
        if (!messageGraphId && Array.isArray(values.messages)) {
          // Look for the most recent metadata that might contain graph_id
          const recentMessages = values.messages.slice(-10); // Check last 10 messages for metadata
          for (const msgItem of recentMessages) {
            if (msgItem && typeof msgItem === 'object' && msgItem.graph_id) {
              messageGraphId = msgItem.graph_id;
              break;
            }
          }
        }
      }
    }
    
    // Method 3: Check if meta contains graph_id information
    if (!messageGraphId && meta) {
      const metaData = meta as any;
      if (metaData.graph_id) {
        messageGraphId = metaData.graph_id;
      }
      if (!messageGraphId && metaData.firstSeenState?.metadata?.graph_id) {
        messageGraphId = metaData.firstSeenState.metadata.graph_id;
      }
      if (!messageGraphId && metaData.firstSeenState?.values?.metadata?.graph_id) {
        messageGraphId = metaData.firstSeenState.values.metadata.graph_id;
      }
    }
    
    // Fallback 1: Use selected assistant's graph_id
    if (!messageGraphId && agentId && agents.length > 0) {
      const selectedAgent = agents.find(agent => agent.assistant_id === agentId);
      if (selectedAgent) {
        messageGraphId = selectedAgent.graph_id;
      }
    }
    
    // Fallback 2: Return undefined to let resolver use "*" for global matching
    return messageGraphId;
  }, [thread.values, message?.id, meta, agentId, agents]);
  
  // Apply lessons learned: Check if this is the last AI message specifically
  const aiMessages = thread.messages.filter((m: any) => m.type === "ai");
  const isLastAIMessage = aiMessages.length > 0 && 
    aiMessages[aiMessages.length - 1].id === message?.id;
  
  // Check if this is the last message overall
  const isLastMessage = message?.id === thread.messages[thread.messages.length - 1]?.id;
  const hasNoAIOrToolMessages = !thread.messages.find(
    (m: any) => m.type === "ai" || m.type === "tool",
  );
  
  const threadInterrupt = thread.interrupt;
  
  // ✅ Implement run completion detection strategy
  // A run is complete when:
  // - Not currently loading new messages
  // - No pending human interrupt (tool approval, etc.)
  const _isRunComplete = !thread.isLoading && !threadInterrupt;
  

  

  const parentCheckpoint = meta?.firstSeenState?.parent_checkpoint;
  const anthropicStreamedToolCalls = Array.isArray(content)
    ? parseAnthropicStreamedToolCalls(content)
    : undefined;

  // Deduplicate tool calls - prioritize regular tool_calls over Anthropic parsed ones
  const regularToolCallIds = new Set(
    (message && "tool_calls" in message && message.tool_calls ? message.tool_calls : [])
      .filter(tc => tc.id && tc.name) // Only valid tool calls
      .map(tc => tc.id) || []
  );
  
  const deduplicatedAnthropicToolCalls = anthropicStreamedToolCalls?.filter(
    tc => !regularToolCallIds.has(tc.id)
  ) || [];

  const hasToolCalls =
    message &&
    "tool_calls" in message &&
    message.tool_calls &&
    message.tool_calls.length > 0;
  const _toolCallsHaveContents =
    hasToolCalls &&
    message.tool_calls?.some(
      (tc) => tc.args && Object.keys(tc.args).length > 0,
    );
  const hasAnthropicToolCalls = deduplicatedAnthropicToolCalls && deduplicatedAnthropicToolCalls.length > 0;
  const hasEarlyToolCalls = hasToolCalls || hasAnthropicToolCalls;
  
  // ✅ Better turn/sequence detection
  // A "turn" consists of: AI message + tool calls + tool results + final AI response
  // Action bars should only show at the END of complete turns
      const { isEndOfCompleteTurn, isPartOfActiveTurn: _isPartOfActiveTurn } = useMemo(() => {
    if (!message?.id) return { isEndOfCompleteTurn: false, isPartOfActiveTurn: false };
    
    // Find this message's index
    const messageIndex = thread.messages.findIndex((m: any) => m.id === message.id);
    if (messageIndex === -1) return { isEndOfCompleteTurn: false, isPartOfActiveTurn: false };
    
    // Look ahead to see if there are tool results or more AI messages following this one
    const messagesAfter = thread.messages.slice(messageIndex + 1);
    const hasToolResultsAfter = messagesAfter.some((m: any) => m.type === "tool");
    const hasAIMessagesAfter = messagesAfter.some((m: any) => m.type === "ai");
    
    // If this AI message has tool calls, check if all tool calls have been resolved
    if (hasEarlyToolCalls && message && "tool_calls" in message && message.tool_calls) {
      // Check if all tool calls have corresponding tool results
      const toolCallIds = message.tool_calls.map((tc: any) => tc.id).filter(Boolean);
      const toolResultsAfter = messagesAfter.filter((m: any) => 
        m.type === "tool" && "tool_call_id" in m && m.tool_call_id && toolCallIds.includes(m.tool_call_id)
      );
      
      const allToolCallsResolved = toolCallIds.length > 0 && 
        toolCallIds.every((id: string) => toolResultsAfter.some((tr: any) => "tool_call_id" in tr && tr.tool_call_id === id));
      
      // If tools aren't resolved, this is part of active turn
      if (!allToolCallsResolved) {
        return { isEndOfCompleteTurn: false, isPartOfActiveTurn: true };
      }
      
      // If tools are resolved but there are more AI messages after, still not end of turn
      if (hasAIMessagesAfter) {
        return { isEndOfCompleteTurn: false, isPartOfActiveTurn: true };
      }
    }
    
    // If currently loading or has interrupt, this could be part of active turn
    if (thread.isLoading || threadInterrupt) {
      return { isEndOfCompleteTurn: false, isPartOfActiveTurn: true };
    }
    
    // If this is the last message and no pending activity, it's end of complete turn
    if (isLastMessage && !hasToolResultsAfter && !hasAIMessagesAfter) {
      return { isEndOfCompleteTurn: true, isPartOfActiveTurn: false };
    }
    
    // If there are no messages after this one, it's complete
    if (messagesAfter.length === 0) {
      return { isEndOfCompleteTurn: true, isPartOfActiveTurn: false };
    }
    
    // Otherwise, this is likely a completed historical turn
    return { isEndOfCompleteTurn: true, isPartOfActiveTurn: false };
  }, [message?.id, thread.messages, hasEarlyToolCalls, message, thread.isLoading, threadInterrupt, isLastMessage]);
  
  const isToolResult = message?.type === "tool";

  // Tool results are now handled by the ToolCallResolver, so we don't render them separately
  if (isToolResult) {
    return null;
  }

  return (
    <div className="group mr-auto flex items-start gap-2 w-full">
      <div className="flex flex-col gap-2 w-full">{/* Fixed: Ensure full width flows down */}
          {(() => {
            // Suppress streaming of control JSON payloads (routing/flags) to avoid jarring UI
            const detection = isStructuredControlJson(contentString, { partial: isLoading });
            const shouldRenderText = contentString.length > 0 && !detection.isLikely;
            if (!shouldRenderText) return null;
            return (
            <div className="py-1">
              <MarkdownText>{contentString}</MarkdownText>
            </div>
            );
          })()}

          {/* Tool calls using new registry system - show immediately when detected */}
          {hasEarlyToolCalls && (
            <div className="space-y-2 w-full">{/* Fixed: Ensure tool calls get full width */}
              {/* Regular tool calls */}
              {hasToolCalls && message.tool_calls && 
                (() => {
                  const matchedItems = matchToolCallsWithResults(
                    message.tool_calls,
                    thread.messages,
                    isLoading
                  );
                  return matchedItems.map((item, idx) => {
                    return (
                      <ToolCallResolver
                        key={item.toolCall.id || idx}
                        toolCall={item.toolCall}
                        toolResult={item.toolResult}
                        state={item.state}
                        streaming={item.streaming}
                        graphId={graphId}
                      />
                    );
                  });
                })()
              }
              
              {/* Anthropic streamed tool calls */}
              {hasAnthropicToolCalls && deduplicatedAnthropicToolCalls && 
                (() => {
                  const matchedItems = matchToolCallsWithResults(
                    deduplicatedAnthropicToolCalls,
                    thread.messages,
                    isLoading
                  );
                  return matchedItems.map((item, idx) => {
                    return (
                      <ToolCallResolver
                        key={item.toolCall.id || idx}
                        toolCall={item.toolCall}
                        toolResult={item.toolResult}
                        state={item.state}
                        streaming={item.streaming}
                        graphId={graphId}
                      />
                    );
                  });
                })()
              }
            </div>
          )}

          {message && (
            <CustomComponent
              message={message}
              thread={thread}
            />
          )}
          {(() => {
            return (
              <Interrupt
                interruptValue={threadInterrupt?.value as any}
                isLastMessage={isLastAIMessage || hasNoAIOrToolMessages}
                hasNoAIOrToolMessages={hasNoAIOrToolMessages}
              />
            );
          })()}
          {(() => {
            // ✅ Implement improved action bar logic 
            // Show action bar only at the end of complete turns
            const shouldShowActionBar = isEndOfCompleteTurn;
            
            if (!shouldShowActionBar) {
              return null;
            }
            
            return (
              <div
                className={cn(
                  "mr-auto flex items-center gap-2 transition-opacity",
                  "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100",
                )}
              >
                <BranchSwitcher
                  branch={meta?.branch}
                  branchOptions={meta?.branchOptions}
                  onSelect={(branch) => thread.setBranch(branch)}
                  isLoading={isLoading}
                />
                <CommandBar
                  content={contentString}
                  isLoading={isLoading}
                  isAiMessage={true}
                  handleRegenerate={() =>
                    handleRegenerate(parentCheckpoint, (prev) => {
                      const values = meta?.firstSeenState?.values;
                      if (!values) return prev;
                      return { ...values, messages: values.messages.slice(0, -1) };
                    })
                  }
                />
              </div>
            );
          })()}
        </div>
    </div>
  );
}

export function AssistantMessageLoading() {
  return (
    <div className="mr-auto flex items-center gap-2">
      <MinimalistBadge
        icon={Loader2}
        tooltip="AI is thinking..."
        className="animate-spin bg-transparent"
      />
      <span className="text-sm text-muted-foreground">
        Thinking...
      </span>
    </div>
  );
}
