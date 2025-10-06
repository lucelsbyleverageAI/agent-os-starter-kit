import { v4 as uuidv4 } from "uuid";
import {
  ReactNode,
  useEffect,
  useMemo,
  useRef,
} from "react";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { useStreamContext } from "@/features/chat/providers/Stream";
import { useState, FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Checkpoint, Message } from "@langchain/langgraph-sdk";
import { AssistantMessage } from "@/features/chat/components/thread/messages/ai";
import { HumanMessage } from "@/features/chat/components/thread/messages/human";
import Image from "next/image";

import {
  ArrowDown,
  AlertCircle,
} from "lucide-react";
import { useQueryState, parseAsBoolean, parseAsString } from "nuqs";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import { toast } from "sonner";

import { DO_NOT_RENDER_ID_PREFIX } from "@/constants";
import { useConfigStore } from "../../hooks/use-config-store";
import { useAuthContext } from "@/providers/Auth";
import { useAgentsContext } from "@/providers/Agents";
import { fetchWithAuth } from "@/lib/auth/fetch-with-auth";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useFileUpload } from "@/hooks/use-file-upload";
import { DynamicInputComposer } from "./DynamicInputComposer";
import { TasksFilesSidebar } from "../tasks-files-sidebar";
import { FileViewDialog } from "../file-view-dialog";
import { useDeepAgentWorkspace } from "@/hooks/use-deep-agent-workspace";
import { FileItem } from "@/types/deep-agent";

function StickyToBottomContent(props: {
  content: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  const context = useStickToBottomContext();
  return (
    <div
      ref={context.scrollRef}
      className={props.className}
    >
      <div
        ref={context.contentRef}
        className={props.contentClassName}
      >
        {props.content}
      </div>
    </div>
  );
}

function ScrollToBottom(props: { className?: string }) {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();

  if (isAtBottom) return null;
  return (
    <Button
      variant="outline"
      className={props.className}
      onClick={() => scrollToBottom()}
    >
      <ArrowDown className="h-4 w-4" />
      <span>Scroll to bottom</span>
    </Button>
  );
}



interface ThreadProps {
  historyOpen?: boolean;
  configOpen?: boolean;
}

export function Thread({ historyOpen = false, configOpen = false }: ThreadProps) {
  const [agentId] = useQueryState("agentId");
  const [agentMismatch] = useQueryState("agentMismatch", parseAsString);
  const [hideToolCalls, setHideToolCalls] = useQueryState(
    "hideToolCalls",
    parseAsBoolean.withDefault(false),
  );
  const [hasInput, setHasInput] = useState(false);
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);
  
  // Deep agent workspace functionality
  const {
    isDeepAgent,
    workspaceData,
    workspaceSidebarCollapsed,
    toggleWorkspaceSidebar,
  } = useDeepAgentWorkspace();
  const {
    contentBlocks,
    setContentBlocks: _setContentBlocks,
    processingAttachments,
    handleFileUpload,
    dropRef,
    removeBlock,
    removeProcessingAttachment,
    resetBlocks,
    dragOver,
    handlePaste,
  } = useFileUpload();
  

  const { session } = useAuthContext();
  const { agents } = useAgentsContext();

  const stream = useStreamContext();
  const [preservedMessages, setPreservedMessages] = useState<Message[]>([]);
  const [threadId] = useQueryState("threadId");
  const lastThreadIdRef = useRef<string | null>(threadId);
  const streamMessages = stream.messages;
  const isLoading = stream.isLoading;
  
  // Track pending first message touch for new threads
  const [pendingFirstMessageTouch, setPendingFirstMessageTouch] = useState<{
    messageContent: string;
    assistantId: string;
    graphId?: string;
    timestamp: string;
  } | null>(null);

  // Use preserved messages only when stream messages are empty and we have preserved ones
  const messages = streamMessages?.length === 0 && preservedMessages.length > 0 ? preservedMessages : streamMessages;

  // Clear protection when thread changes
  useEffect(() => {
    if (threadId !== lastThreadIdRef.current) {
      setPreservedMessages([]);
      lastThreadIdRef.current = threadId;
    }
  }, [threadId]);

  // Handle pending first message touch when threadId becomes available
  useEffect(() => {
    if (threadId && pendingFirstMessageTouch && session?.accessToken) {
      const { messageContent, assistantId, graphId, timestamp } = pendingFirstMessageTouch;
      
      
      const touchPayload = {
        thread_id: threadId,
        assistant_id: assistantId || undefined,
        graph_id: graphId || undefined,
        status: 'busy',
        name_if_absent: messageContent,
        last_message_at: timestamp,
      };


      fetchWithAuth('/api/langconnect/agents/mirror/threads/touch', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(touchPayload),
      }, session)
      .then(response => response.json())
      .then(result => {
        // Clear the pending touch
        setPendingFirstMessageTouch(null);
        // Trigger a refresh of thread lists
        try {
          const threadsVersion = (result && (result.threads_version || result.threadsVersion)) as number | undefined;
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('refreshThreads', { detail: { threadId, threadsVersion } }));
          }, 100);
          // Second-chance refresh to avoid race with listener mounting or mirror lag
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('refreshThreads', { detail: { threadId, threadsVersion } }));
          }, 800);
        } catch {
      // Ignore touch errors
    }
      })
      .catch((err) => {
        console.error('[threads:touch] first message error', err);
        // Clear the pending touch even on error to avoid retry loops
        setPendingFirstMessageTouch(null);
      });
    }
  }, [threadId, pendingFirstMessageTouch, session?.accessToken]);

  // Store messages when we have them, add new messages when they arrive
  useEffect(() => {
    if (streamMessages?.length > 0) {
      setPreservedMessages([...streamMessages]);
    }
  }, [streamMessages]);

  // Detect unintentional message drops within the same thread
  useEffect(() => {
    if (streamMessages?.length === 0 && preservedMessages.length > 0 && threadId === lastThreadIdRef.current) {
      // Message drop detected
    }
  }, [streamMessages, preservedMessages, threadId]);

  // Debug: log message changes
  useEffect(() => {
    const _usingPreserved = streamMessages?.length === 0 && preservedMessages.length > 0;
    if (messages?.length === 0) {
      // No messages to log
    }
  }, [messages, isLoading, stream.interrupt, streamMessages, preservedMessages]);

  const lastError = useRef<string | undefined>(undefined);
  const [errorMessage, setErrorMessage] = useState("");

  // Calculate dynamic width based on sidebar states
  const chatWidth = useMemo(() => {
    // Mobile-first responsive widths - no max-width on mobile, progressively wider on larger screens
    return cn(
      "w-full mx-auto",
      "md:max-w-3xl",   // Tablet and up: 768px
      "lg:max-w-4xl",   // Desktop: 1024px  
      "xl:max-w-5xl",   // Large desktop: 1280px
      "2xl:max-w-6xl",  // Extra large: 1536px
    );
  }, [historyOpen, configOpen]);

  useEffect(() => {
    if (!stream.error) {
      lastError.current = undefined;
      setErrorMessage("");
      return;
    }
    try {
      const message = (stream.error as any).message;
      if (!message || lastError.current === message) {
        // Message has already been logged. do not modify ref, return early.
        return;
      }

      // Message is defined, and it has not been logged yet. Save it, and send the error
      lastError.current = message;
      setErrorMessage(message);
      toast.error("An error occurred. Please try again.", {
        description: (
          <p>
            <strong>Error:</strong> <code>{message}</code>
          </p>
        ),
        richColors: true,
        closeButton: true,
      });
    } catch {
      // no-op
    }
  }, [stream.error]);

  // TODO: this should be part of the useStream hook
  const prevMessageLength = useRef(0);
  useEffect(() => {
    prevMessageLength.current = messages.length;
  }, [messages]);

  // On stream completion (heuristic: last message is AI and not loading), touch mirror as idle
  useEffect(() => {
    try {
      const last = messages[messages.length - 1] as Message | undefined;
      if (!last || last.type !== 'ai') return;
      // Touch as idle shortly after AI message arrives
      const timer = setTimeout(() => {
        if (session?.accessToken && threadId) {
          const currentAgent = agents.find(a => a.assistant_id === agentId);
          const graphId = currentAgent?.graph_id;
          
          fetchWithAuth('/api/langconnect/agents/mirror/threads/touch', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              thread_id: threadId,
              assistant_id: agentId || undefined,
              graph_id: graphId || undefined,
              status: 'idle',
              last_message_at: new Date().toISOString(),
            }),
          }, session).then(() => {
            // Stream completion doesn't need to refresh sidebar - just updates status
          }).catch(() => {});
        }
      }, 300);
      return () => clearTimeout(timer);
    } catch {
      // Ignore touch errors
    }
  }, [messages, threadId, session?.accessToken, agentId, agents]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();

    const form = e.currentTarget as HTMLFormElement;
    const formData = new FormData(form);
    const content = (formData.get("input") as string | undefined)?.trim() ?? "";

    setHasInput(false);
    if (!agentId) return;
    if (
      (content.trim().length === 0 && contentBlocks.length === 0) ||
      isLoading
    )
      return;

    

    const newHumanMessage: Message = {
      id: uuidv4(),
      type: "human",
      content: [
        ...(content.trim().length > 0 ? [{ type: "text", text: content }] : []),
        ...contentBlocks,
      ] as Message["content"],
    };

    // TEMPORARILY DISABLED: ensureToolCallsHaveResponses function
    // const toolMessages = ensureToolCallsHaveResponses(stream.messages);
    const toolMessages: Message[] = []; // No additional tool messages needed
    const { getAgentConfig } = useConfigStore.getState();

    stream.submit(
      { messages: [...stream.messages, ...toolMessages, newHumanMessage] },
      {
        streamMode: ["values"],
        optimisticValues: (prev: { messages?: Message[] }) => ({
          ...prev,
          messages: [
            ...(prev.messages ?? []),
            ...toolMessages,
            newHumanMessage,
          ],
        }),
        config: {
          configurable: getAgentConfig(agentId),
        },
        metadata: {
          supabaseAccessToken: session?.accessToken,
        },
      },
    );

    // Fire-and-forget mirror touch to create/update the thread list entry immediately
    try {
      const nowIso = new Date().toISOString();
      const assistantId = agentId || '';
      const currentThreadId = (window.location.search.match(/threadId=([^&]+)/)?.[1] || '') || (stream as any)?.threadId || '';
      
      // Get the current agent from the agents context to get graph_id
      const currentAgent = agents.find(a => a.assistant_id === agentId);
      const graphId = currentAgent?.graph_id;
      
      
      // Extract first human message content for naming
      const nameIfAbsent = (newHumanMessage.content as any[])
        .filter((c) => c?.type === 'text')
        .map((c) => c.text)
        .join(' ')
        .slice(0, 80);
      
      if (currentThreadId && session?.accessToken) {
        // Existing thread - touch immediately
        const touchPayload = {
          thread_id: currentThreadId,
          assistant_id: assistantId || undefined,
          graph_id: graphId || undefined,
          status: 'busy',
          name_if_absent: nameIfAbsent,
          last_message_at: nowIso,
        };
        
       
        
        fetchWithAuth('/api/langconnect/agents/mirror/threads/touch', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(touchPayload),
        }, session)
        .then(response => response.json())
        .then(result => {
          
          // Trigger a lightweight refresh so sidebars pick up latest order/name
          try {
            const threadsVersion = (result && (result.threads_version || result.threadsVersion)) as number | undefined;
            window.dispatchEvent(new CustomEvent('refreshThreads', { detail: { threadId: currentThreadId, threadsVersion } }));
            setTimeout(() => {
              window.dispatchEvent(new CustomEvent('refreshThreads', { detail: { threadId: currentThreadId, threadsVersion } }));
            }, 800);
          } catch {
      // Ignore touch errors
    }
        })
        .catch((err) => {
          console.error('[threads:touch] error', err);
        });
      } else if (!currentThreadId && nameIfAbsent) {
        // New thread - set up pending touch for when threadId becomes available
        
        setPendingFirstMessageTouch({
          messageContent: nameIfAbsent,
          assistantId,
          graphId,
          timestamp: nowIso,
        });
      }
    } catch (err) {
      console.error('[threads:touch] exception', err);
    }

    // Reset form and clear attachments
    const formElement = document.querySelector('form') as HTMLFormElement;
    if (formElement) formElement.reset();
    resetBlocks();
  };



  const handleRegenerate = (
    parentCheckpoint: Checkpoint | null | undefined,
    optimisticValues?: (prev: { messages?: Message[] }) => {
      messages?: Message[] | undefined;
    },
  ) => {
    if (!agentId) return;
    const { getAgentConfig } = useConfigStore.getState();

    // Do this so the loading state is correct
    prevMessageLength.current = prevMessageLength.current - 1;
    
    stream.submit(undefined, {
      checkpoint: parentCheckpoint,
      streamMode: ["values"],
      config: {
        configurable: getAgentConfig(agentId),
      },
      optimisticValues,
      metadata: {
        supabaseAccessToken: session?.accessToken,
      },
    });
  };

  const hasMessages = messages.length > 0;
  const hasNoAIOrToolMessages = !messages.find(
    (m: Message) => m.type === "ai" || m.type === "tool",
  );

  return (
    <>
      <div className="flex flex-1 min-h-0 w-full overflow-hidden">
        {/* Deep Agent Workspace Sidebar - Left Side */}
        {(() => {
          
          return isDeepAgent && (
            <TasksFilesSidebar
              todos={workspaceData.todos}
              files={workspaceData.files}
              onFileClick={setSelectedFile}
              collapsed={workspaceSidebarCollapsed}
              onToggleCollapse={toggleWorkspaceSidebar}
            />
          );
        })()}

        <StickToBottom className="flex flex-1 min-h-0 flex-col overflow-hidden">
          <div className={cn(
            "flex flex-1 min-h-0 flex-col",
            !hasMessages && "items-center justify-center"
          )}>
            {!hasMessages ? (
              // Empty state: centered logo and composer
              <div className={cn("flex flex-col items-center gap-8 px-2 md:px-4 w-full", chatWidth)}>
                <div className="flex items-center justify-center gap-3">
                  <Image 
                    src="/logo_icon_round.png" 
                    alt="AgentOS Logo" 
                    width={48} 
                    height={48} 
                    priority
                    unoptimized
                    className="flex-shrink-0"
                  />
                  <h1 className="text-3xl font-semibold tracking-tight">
                    AgentOS
                  </h1>
                </div>

                <div className="relative w-full">
                  <DynamicInputComposer
                    dropRef={dropRef}
                    chatWidth="w-full"
                    dragOver={dragOver}
                    handleSubmit={handleSubmit}
                    contentBlocks={contentBlocks}
                    processingAttachments={processingAttachments}
                    removeBlock={removeBlock}
                    removeProcessingAttachment={removeProcessingAttachment}
                    setHasInput={setHasInput}
                    handlePaste={handlePaste}
                    hasMessages={hasMessages}
                    hideToolCalls={hideToolCalls}
                    setHideToolCalls={setHideToolCalls}
                    handleFileUpload={handleFileUpload}
                    isLoading={isLoading}
                    hasInput={hasInput}
                    onStop={() => stream.stop()}
                  />
                </div>
              </div>
            ) : (
              // Messages state: scrollable content with sticky composer
              <>
                <StickyToBottomContent
                  className={cn(
                    "flex-1 overflow-y-auto overflow-x-hidden px-2 md:px-4",
                    ...getScrollbarClasses('y'),
                  )}
                  contentClassName={cn(
                    "flex flex-col gap-4 w-full pt-8 pb-4",
                    chatWidth
                  )}
                  content={
                  <>
                    {/* Agent Mismatch Warning Banner */}
                {agentMismatch === "true" && (
                  <Alert variant="default" className="border-orange-200 bg-orange-50">
                    <AlertCircle className="h-4 w-4 text-orange-600" />
                    <AlertTitle className="text-orange-800">Agent Mismatch Warning</AlertTitle>
                    <AlertDescription className="text-orange-700">
                      The original agent for this conversation was deleted. You're now using a fallback agent, 
                      so the conversation may not work as expected. Consider starting a new chat for the best experience.
                    </AlertDescription>
                  </Alert>
                )}
                
                {messages
                  .filter((m: Message) => !m.id?.startsWith(DO_NOT_RENDER_ID_PREFIX))
                  .map((message: Message, index: number) =>
                    message.type === "human" ? (
                      <HumanMessage
                        key={message.id || `${message.type}-${index}`}
                        message={message}
                        isLoading={isLoading}
                      />
                    ) : (
                      <AssistantMessage
                        key={message.id || `${message.type}-${index}`}
                        message={message}
                        isLoading={isLoading}
                        handleRegenerate={handleRegenerate}
                      />
                    ),
                  )}
                {/* Special rendering case where there are no AI/tool messages, but there is an interrupt.
                      We need to render it outside of the messages list, since there are no messages to render */}
                {(() => {
                  if (hasNoAIOrToolMessages && !!stream.interrupt) {
                    return (
                      <AssistantMessage
                        key="interrupt-msg"
                        message={undefined}
                        isLoading={isLoading}
                        handleRegenerate={handleRegenerate}
                      />
                    );
                  }
                  return null;
                })()}
                {isLoading && (
                  <div className="mr-auto flex items-center gap-2 py-1">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
                  </div>
                )}
                {errorMessage && (
                  <Alert variant="destructive">
                    <AlertCircle className="size-4" />
                    <AlertTitle>An error occurred:</AlertTitle>
                    <AlertDescription>{errorMessage}</AlertDescription>
                  </Alert>
                )}
              </>
            }
                />
                
                <div className="flex shrink-0 flex-col items-center gap-4 bg-background px-2 md:px-4 pb-4">
                  <div className="relative w-full">
                    <ScrollToBottom className="animate-in fade-in-0 zoom-in-95 absolute bottom-full left-1/2 mb-4 -translate-x-1/2" />

                    <DynamicInputComposer
                      dropRef={dropRef}
                      chatWidth={chatWidth}
                      dragOver={dragOver}
                      handleSubmit={handleSubmit}
                      contentBlocks={contentBlocks}
                      processingAttachments={processingAttachments}
                      removeBlock={removeBlock}
                      removeProcessingAttachment={removeProcessingAttachment}
                      setHasInput={setHasInput}
                      handlePaste={handlePaste}
                      hasMessages={hasMessages}
                      hideToolCalls={hideToolCalls}
                      setHideToolCalls={setHideToolCalls}
                      handleFileUpload={handleFileUpload}
                      isLoading={isLoading}
                      hasInput={hasInput}
                      onStop={() => stream.stop()}
                    />
                  </div>
                </div>
              </>
            )}
          </div>
        </StickToBottom>

      </div>

      {/* File View Dialog */}
      {selectedFile && (
        <FileViewDialog
          file={selectedFile}
          onClose={() => setSelectedFile(null)}
        />
      )}
    </>
  );
}
