"use client";

import { cn } from "@/lib/utils";
import { Message, Thread } from "@langchain/langgraph-sdk";
import { useEffect, useState, forwardRef, ForwardedRef } from "react";
import { useQueryState } from "nuqs";
// import { createClient } from "@/lib/client"; // Removed unused import
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { format } from "date-fns";
import { useAuthContext } from "@/providers/Auth";
import { MessageContent } from "@langchain/core/messages";
import { FileClock, X } from "lucide-react";
import { ThreadActionMenu } from "@/components/ui/thread-action-menu";
import { ThreadDeleteDialog } from "@/components/ui/confirmation-dialog";
import { useThreadDeletion } from "@/hooks/use-thread-deletion";
import { notify } from "@/utils/toast";
import { threadMessages } from "@/utils/toast-messages";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { Button } from "@/components/ui/button";

const getMessageStringContent = (
  content: MessageContent | undefined,
): string => {
  if (!content) return "";
  if (typeof content === "string") return content;
  const texts = content
    .filter((c): c is { type: "text"; text: string } => c.type === "text")
    .map((c) => c.text);
  return texts.join(" ");
};

/**
 * Returns the first human message from a thread
 * @param thread The thread to get the first human message from
 * @returns The first human message content, or an empty string if no human message is found
 */
function getFirstHumanMessageContent(thread: Thread) {
  try {
    if (
      Array.isArray(thread.values) ||
      !("messages" in thread.values) ||
      !thread.values.messages ||
      !Array.isArray(thread.values.messages) ||
      !thread.values.messages.length
    )
      return "";
    const castMessages = thread.values.messages as Message[];

    const firstHumanMsg = castMessages.find((msg) => msg.type === "human");
    return getMessageStringContent(firstHumanMsg?.content);
  } catch (e) {
    console.error("Failed to get human message from thread", {
      thread,
      error: e,
    });
    return "";
  }
}

const formatDate = (date: string) => {
  try {
    return format(new Date(date), "MM/dd/yyyy - h:mm a");
  } catch (e) {
    console.error("Failed to format date", { date, error: e });
    return "";
  }
};

export interface ThreadHistorySidebarProps {
  className?: string;
  open: boolean;
  setOpen: (open: boolean) => void;
}

export const ThreadHistorySidebar = forwardRef<
  HTMLDivElement,
  ThreadHistorySidebarProps
>(({ className, open, setOpen }, ref: ForwardedRef<HTMLDivElement>) => {
  const { session, isLoading: authLoading } = useAuthContext();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadId, setThreadId] = useQueryState("threadId");
  const [agentId] = useQueryState("agentId");
  const [deploymentId] = useQueryState("deploymentId");
  const [loading, setLoading] = useState(false);
  
  // Thread deletion state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [threadToDelete, setThreadToDelete] = useState<Thread | null>(null);
  const { deleteThread, isDeleting } = useThreadDeletion();
  
  // Thread rename state
  const [renamingThreadId, setRenamingThreadId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState<string>("");
  const [isRenaming, setIsRenaming] = useState(false);

  // Store the refresh function so it can be called externally
  const refreshThreads = async (threadsVersion?: number) => {
    if (authLoading || !agentId || !session?.accessToken) return;

    setLoading(true);
    try {
      const url = new URL(`/api/langconnect/agents/mirror/threads`, window.location.origin);
      url.searchParams.set('assistant_id', agentId);
      url.searchParams.set('limit', '20');
      if (threadsVersion != null) url.searchParams.set('v', String(threadsVersion));
      const resp = await fetch(url.toString(), {
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        }
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`Mirror threads fetch failed: ${resp.status} ${text}`);
      }
      const data = await resp.json();
      // Map mirror thread shape to SDK Thread-like minimal structure for current rendering (id, updated_at, values/messages for title)
      const mapped: Thread[] = (data.threads || []).map((t: any) => ({
        thread_id: t.thread_id,
        created_at: t.created_at,
        updated_at: t.updated_at || t.last_message_at || t.created_at,
        // Provide minimal values shape so getFirstHumanMessageContent can still work if needed (fallback empty)
        values: { messages: [] } as any,
        status: (t.status as any) || 'idle',
        // Attach name from mirror so UI can display it immediately
        name: t.name,
      }));
      setThreads(mapped);
    } catch (e) {
      console.error("Failed to fetch threads (mirror)", e);
      toast.error("Failed to fetch threads");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshThreads();
  }, [agentId, authLoading, session?.accessToken]);

  // Refresh threads when threadId changes (indicating a new thread was created)
  useEffect(() => {
    if (threadId) {
      // Delay refresh to allow backend to process the touch call
      const timer = setTimeout(() => {
        refreshThreads();
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [threadId]);

  // Listen for custom refresh events triggered after thread creation
  useEffect(() => {
    const handleRefreshThreads = (e: any) => {  
      try {
        const v = e?.detail?.threadsVersion as number | undefined;
        refreshThreads(v);
      } catch {
        refreshThreads();
      }
    };

    window.addEventListener('refreshThreads', handleRefreshThreads);
    return () => window.removeEventListener('refreshThreads', handleRefreshThreads);
  }, [agentId, session?.accessToken]); // Only depend on the values refreshThreads needs

  const handleChangeThread = (id: string) => {
    if (threadId === id) return;
    setThreadId(id);
    setOpen(false);
  };

  // Handle thread deletion
  const handleDeleteThread = (thread: Thread) => {
    setThreadToDelete(thread);
    setDeleteDialogOpen(true);
  };

  const confirmDeleteThread = async () => {
    if (!threadToDelete || !deploymentId) return;

    const result = await deleteThread(threadToDelete.thread_id, deploymentId);
    
    if (result.ok) {
      // Remove thread from local state
      setThreads(prev => prev.filter(t => t.thread_id !== threadToDelete.thread_id));
      
      // Check if we need to navigate away from the current thread
      if (threadId === threadToDelete.thread_id) {
        // Navigate to new thread (clear threadId)
        setThreadId(null);
      }

      // Show success message
      const message = threadMessages.delete.success();
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });
    } else {
      // Show error message
      const message = threadMessages.delete.error(result.errorMessage);
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
    }

    setDeleteDialogOpen(false);
    setThreadToDelete(null);
  };

  // Handle thread renaming
  const handleRenameThread = (thread: Thread) => {
    const currentName = (thread as any).name || getFirstHumanMessageContent(thread) || "New chat";
    setRenamingThreadId(thread.thread_id);
    setRenameValue(currentName);
  };

  const confirmRename = async () => {
    if (!renamingThreadId || !renameValue.trim()) return;
    
    setIsRenaming(true);
    try {
      const response = await fetch(`/api/langconnect/agents/mirror/threads/${renamingThreadId}/rename`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session?.accessToken}`,
        },
        body: JSON.stringify({ new_name: renameValue.trim() }),
      });

      if (!response.ok) {
        throw new Error(`Failed to rename thread: ${response.status}`);
      }

      const result = await response.json();
      
      // Update local state
      setThreads(prev => prev.map(t => 
        t.thread_id === renamingThreadId 
          ? { ...t, name: result.new_name } as any
          : t
      ));
      
      // Reset rename state
      setRenamingThreadId(null);
      setRenameValue("");
      
      // No need to refresh other components - rename only changes display name
      // The local state update above is sufficient
      
    } catch (error) {
      console.error("Failed to rename thread:", error);
    } finally {
      setIsRenaming(false);
    }
  };

  const cancelRename = () => {
    setRenamingThreadId(null);
    setRenameValue("");
  };

  return (
    <div
      ref={ref}
      className={cn(
        "fixed top-0 right-0 z-10 h-screen border-l bg-background dark:bg-background shadow-lg transition-all duration-300",
        open ? "w-80 md:w-[36rem]" : "w-0 overflow-hidden border-l-0",
        className,
      )}
    >
      {open && (
        <div className="flex h-full flex-col">
          <div className="flex flex-shrink-0 items-center justify-between border-b p-4">
            <h2 className="text-lg font-semibold tracking-tight">History</h2>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setOpen(false)}
              className="h-8 w-8"
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Close history</span>
            </Button>
          </div>

          {loading ? (
            <div className="flex flex-1 items-center justify-center p-4">
              {Array.from({ length: 10 }).map((_, index) => (
                <Skeleton
                  key={`thread-loading-${index}`}
                  className="h-8 w-full"
                />
              ))}
            </div>
          ) : (
            <div className={cn("flex-1", ...getScrollbarClasses('y'))}>
              {threads.length === 0 && (
                <div className="flex h-full flex-1 items-center justify-center gap-2">
                  <FileClock className="size-6" />
                  <p>No threads found</p>
                </div>
              )}
              {threads
                .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
                .map((thread) => {
                const isSelected = thread.thread_id === threadId;
                return (
                  <div
                    key={thread.thread_id}
                    className={cn(
                      "group flex items-center justify-between p-4 transition-all duration-300 hover:cursor-pointer hover:bg-accent border-l-2 border-transparent",
                      isSelected
                        ? "bg-muted hover:cursor-default hover:bg-muted border-l-primary"
                        : "",
                    )}
                    onClick={() => handleChangeThread(thread.thread_id)}
                  >
                    <div className="flex items-center flex-1 min-w-0">
                      <div className="flex flex-col min-w-0 flex-1">
                        {/* Thread name with inline editing */}
                        {renamingThreadId === thread.thread_id ? (
                          <Input
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                confirmRename();
                              } else if (e.key === 'Escape') {
                                cancelRename();
                              }
                              e.stopPropagation();
                            }}
                            onBlur={confirmRename}
                            onClick={(e) => e.stopPropagation()}
                            className="h-6 text-sm border-0 bg-transparent p-0 focus-visible:ring-1 focus-visible:ring-ring"
                            autoFocus
                            disabled={isRenaming}
                          />
                        ) : (
                          <p className="line-clamp-1 truncate text-sm font-medium">
                            {(thread as any).name || getFirstHumanMessageContent(thread) || "New chat"}
                          </p>
                        )}
                        <p className="text-sm text-muted-foreground">
                          Last updated: {formatDate(thread.updated_at)}
                        </p>
                      </div>
                    </div>
                    <ThreadActionMenu
                      onDelete={() => handleDeleteThread(thread)}
                      onRename={() => handleRenameThread(thread)}
                      disabled={isDeleting || isRenaming}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
      
      {/* Thread Delete Confirmation Dialog */}
      <ThreadDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        onConfirm={confirmDeleteThread}
        isLoading={isDeleting}
      />
    </div>
  );
});

ThreadHistorySidebar.displayName = "ThreadHistorySidebar";
