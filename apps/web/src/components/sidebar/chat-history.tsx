"use client";

import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { Thread } from "@langchain/langgraph-sdk";
import { format, isToday as _isToday, isThisWeek as _isThisWeek, isThisMonth as _isThisMonth, startOfDay, subDays } from "date-fns";
import { Clock, ChevronDown, ChevronRight, Plus, FileClock, Check, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuthContext } from "@/providers/Auth";
import { useAgentsContext } from "@/providers/Agents";
// import { createClient } from "@/lib/client"; // Removed unused import
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { isUserSpecifiedDefaultAgent, isPrimaryAssistant, groupAgentsByGraphs, isUserCreatedDefaultAssistant, sortAgentGroup } from "@/lib/agent-utils";
import { usePersistedExpandedGroups } from "@/hooks/use-persisted-expanded-groups";
import {
  Select as _Select,
  SelectContent as _SelectContent,
  SelectItem as _SelectItem,
  SelectTrigger as _SelectTrigger,
  SelectValue as _SelectValue,
} from "@/components/ui/select";
import {
  Command,
  CommandEmpty,
  CommandGroup as _CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { getDeployments } from "@/lib/environment/deployments";
import { useRouter } from "next/navigation";
import { MessageContent } from "@langchain/core/messages";
import { Message } from "@langchain/langgraph-sdk";
import {
  SidebarGroup,
  SidebarGroupContent as _SidebarGroupContent,
  SidebarGroupLabel as _SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from "@/components/ui/sidebar";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { ThreadActionMenu } from "@/components/ui/thread-action-menu";
import { ThreadDeleteDialog } from "@/components/ui/confirmation-dialog";
import { useThreadDeletion } from "@/hooks/use-thread-deletion";
import { notify } from "@/utils/toast";
import { threadMessages } from "@/utils/toast-messages";
import * as Sentry from "@sentry/nextjs";

// Function to convert graph_id to human-readable name
const getGraphDisplayName = (graphId: string): string => {
  return graphId
    .replace(/_/g, ' ') // replace all underscores
    .replace(/\b\w/g, l => l.toUpperCase()); // capitalise each word
};

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
  } catch (_e) {
    // Silently handle cases where thread has no messages or invalid structure
    return "";
  }
}

/**
 * Groups threads by time periods
 */
function groupThreadsByTime(threads: Thread[]) {
  const now = new Date();
  const today = startOfDay(now);
  const yesterday = startOfDay(subDays(now, 1));
  const sevenDaysAgo = subDays(today, 7);
  const thirtyDaysAgo = subDays(today, 30);

  const groups: Record<string, Thread[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    "Previous 30 Days": [],
  };

  // Monthly groups will be added dynamically
  const monthlyGroups: Record<string, Thread[]> = {};

  threads.forEach((thread) => {
    const threadDate = new Date(thread.updated_at);
    const threadStartOfDay = startOfDay(threadDate);
    
    if (threadStartOfDay.getTime() === today.getTime()) {
      groups.Today.push(thread);
    } else if (threadStartOfDay.getTime() === yesterday.getTime()) {
      groups.Yesterday.push(thread);
    } else if (threadDate >= sevenDaysAgo) {
      groups["Previous 7 Days"].push(thread);
    } else if (threadDate >= thirtyDaysAgo) {
      groups["Previous 30 Days"].push(thread);
    } else {
      // Group by month for older threads
      const monthKey = format(threadDate, "MMMM yyyy");
      if (!monthlyGroups[monthKey]) {
        monthlyGroups[monthKey] = [];
      }
      monthlyGroups[monthKey].push(thread);
    }
  });

  // Combine groups with monthly groups
  const allGroups = { ...groups, ...monthlyGroups };

  // Filter out empty groups and return in order
  const orderedGroupKeys = [
    "Today",
    "Yesterday",
    "Previous 7 Days", 
    "Previous 30 Days",
    ...Object.keys(monthlyGroups).sort((a, b) => {
      // Sort months in descending order (most recent first)
      return new Date(b).getTime() - new Date(a).getTime();
    })
  ];

  return orderedGroupKeys
    .filter(key => allGroups[key]?.length > 0)
    .map(key => ({
      name: key,
      threads: allGroups[key].sort((a, b) => 
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      )
    }));
}

export function ChatHistory() {
  const { session, isLoading: authLoading } = useAuthContext();
  const { agents, discoveryData } = useAgentsContext();
  const graphNameById = useMemo(() => {
    const map: Record<string, string> = {};
    const graphs = discoveryData?.valid_graphs || [];
    for (const g of graphs) {
      if (g?.name) map[g.graph_id] = g.name;
    }
    return map;
  }, [discoveryData?.valid_graphs]);
  const router = useRouter();
  const deployments = getDeployments();

  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedAgentValue, setSelectedAgentValue] = useState<string>("all");
  const [expandedGroups, setExpandedGroups] = usePersistedExpandedGroups();
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestSeqRef = useRef(0);
  const selectedAgentRef = useRef<string>("all");
  const latestThreadsVersionRef = useRef<number | undefined>(undefined);
  // Background cache of "All Agents" results to avoid stale UI when switching filters
  const allThreadsCacheRef = useRef<Thread[] | null>(null);
  
  // Agent filter popover state
  const [filterOpen, setFilterOpen] = useState(false);
  
  // Thread deletion state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [threadToDelete, setThreadToDelete] = useState<Thread | null>(null);
  const { deleteThread, isDeleting } = useThreadDeletion();
  
  // Thread rename state
  const [renamingThreadId, setRenamingThreadId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState<string>("");
  const [isRenaming, setIsRenaming] = useState(false);

  // Fetch threads for all agents or filtered by agent using mirror endpoints
  const fetchThreads = useCallback(async (agentFilter?: string, append = false, threadsVersion?: number) => {
    if (authLoading || !session?.accessToken) return;

    setLoading(true);
    try {
      // Abort any in-flight request and start a new one
      if (abortControllerRef.current) {
        try { abortControllerRef.current.abort(); } catch { void 0; }
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const reqId = ++requestSeqRef.current;

      let allThreads: Thread[] = [];
      const currentOffset = append ? offset : 0;

      // Use latest known threads version to bust caches if none explicitly provided
      const versionToUse = threadsVersion ?? latestThreadsVersionRef.current;

      if (agentFilter === "all" || !agentFilter) {
        // Fetch threads from mirror (all agents for current user)
        const url = new URL(`/api/langconnect/agents/mirror/threads`, window.location.origin);
        url.searchParams.set('limit', '100');
        url.searchParams.set('offset', currentOffset.toString());
        if (versionToUse != null) url.searchParams.set('v', String(versionToUse));
        
        Sentry.logger.info('[threads:main-history] fetch all', { url: url.toString() });
        const resp = await fetch(url.toString(), {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
          signal: controller.signal,
        });
        
        if (!resp.ok) {
          // If 404, it's a valid case for a new user with no threads
          if (resp.status === 404) {
            allThreads = [];
          } else {
            const text = await resp.text().catch(() => '');
            throw new Error(`Mirror threads fetch failed: ${resp.status} ${text}`);
          }
        } else {
          const data = await resp.json();
          
          // Map mirror thread shape to SDK Thread-like structure
          allThreads = (data.threads || []).map((t: any) => ({
            thread_id: t.thread_id,
            created_at: t.created_at,
            updated_at: t.updated_at || t.last_message_at || t.created_at,
            values: { messages: [] } as any,
            status: (t.status as any) || 'idle',
            name: t.name,
            metadata: {
              assistant_id: t.assistant_id,
            },
          }));
        }
      } else {
        // Fetch threads for specific agent using mirror
        const [agentId, _deploymentId] = agentFilter.split(":");
        const url = new URL(`/api/langconnect/agents/mirror/threads`, window.location.origin);
        url.searchParams.set('assistant_id', agentId);
        url.searchParams.set('limit', '100');
        url.searchParams.set('offset', currentOffset.toString());
        if (versionToUse != null) url.searchParams.set('v', String(versionToUse));
        
        const resp = await fetch(url.toString(), {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
          signal: controller.signal,
        });
        
        if (!resp.ok) {
          // If 404, it's a valid case for a new user with no threads
          if (resp.status === 404) {
            allThreads = [];
          } else {
            const text = await resp.text().catch(() => '');
            throw new Error(`Mirror threads fetch failed: ${resp.status} ${text}`);
          }
        } else {
          const data = await resp.json();
          
          // Map mirror thread shape to SDK Thread-like structure
          allThreads = (data.threads || []).map((t: any) => ({
            thread_id: t.thread_id,
            created_at: t.created_at,
            updated_at: t.updated_at || t.last_message_at || t.created_at,
            values: { messages: [] } as any,
            status: (t.status as any) || 'idle',
            name: t.name,
            metadata: {
              assistant_id: t.assistant_id,
            },
          }));
        }
      }

      // Backend already returns threads ordered by langgraph_updated_at DESC
      // No need for additional client-side sorting
      // Ignore stale responses
      if (reqId !== requestSeqRef.current) {
        return;
      }

      if (append) {
        setThreads(prev => [...prev, ...allThreads]);
      } else {
        setThreads(allThreads);
        setOffset(0);
      }

      setHasMore(allThreads.length === 100);
      if (append) {
        setOffset(prev => prev + allThreads.length);
      }
    } catch (e: any) {
      // Silently ignore intentional aborts
      if (e?.name === 'AbortError' || e === 'unmount') {
        return;
      }
      console.error("Failed to fetch threads", e);
      toast.error("Failed to fetch thread history");
    } finally {
      setLoading(false);
    }
  }, [authLoading, session?.accessToken, offset]);

  // Helper: Fetch "All Agents" list without mutating UI state (used to warm background cache)
  const fetchAllThreadsSilently = useCallback(async (threadsVersion?: number): Promise<Thread[] | null> => {
    if (authLoading || !session?.accessToken) return null;
    try {
      const versionToUse = threadsVersion ?? latestThreadsVersionRef.current;
      const url = new URL(`/api/langconnect/agents/mirror/threads`, window.location.origin);
      url.searchParams.set('limit', '100');
      url.searchParams.set('offset', '0');
      if (versionToUse != null) url.searchParams.set('v', String(versionToUse));
      const resp = await fetch(url.toString(), {
        headers: { Authorization: `Bearer ${session.accessToken}` },
      });
      if (!resp.ok) return null;
      const data = await resp.json();
      const mapped: Thread[] = (data.threads || []).map((t: any) => ({
        thread_id: t.thread_id,
        created_at: t.created_at,
        updated_at: t.updated_at || t.last_message_at || t.created_at,
        values: { messages: [] } as any,
        status: (t.status as any) || 'idle',
        name: t.name,
        metadata: { assistant_id: t.assistant_id },
      }));
      return mapped;
    } catch {
      return null;
    }
  }, [authLoading, session?.accessToken]);

  // Initial load
  useEffect(() => {
    fetchThreads("all");
    return () => {
      if (abortControllerRef.current) {
        try { abortControllerRef.current.abort('unmount'); } catch { void 0; }
      }
    };
  }, [fetchThreads]);

  // Listen for custom refresh events triggered after thread creation
  useEffect(() => {
    const handleRefreshThreads = (e: any) => {
      // Simple approach: reset pagination state and trigger a re-fetch
      setOffset(0);
      setHasMore(true);
      setThreads([]);
      try {
        const v = e?.detail?.threadsVersion as number | undefined;
        // Persist latest version so future fetches (including after filter toggles) carry it
        if (v != null) {
          latestThreadsVersionRef.current = v;
        }
        const currentFilter = selectedAgentRef.current;
        const agentFilter = currentFilter === "all" ? undefined : currentFilter;
        fetchThreads(agentFilter, false, v);
        // Also warm the "All Agents" cache in the background so switching filters shows fresh data
        fetchAllThreadsSilently(v).then((all) => {
          if (all) {
            allThreadsCacheRef.current = all;
          }
        }).catch(() => void 0);
      } catch { void 0; }
    };

    window.addEventListener('refreshThreads', handleRefreshThreads);
    return () => window.removeEventListener('refreshThreads', handleRefreshThreads);
  }, []); // No dependencies - stable event listener
  
  // Keep the ref in sync with the current selected agent value to avoid stale closures
  useEffect(() => {
    selectedAgentRef.current = selectedAgentValue;
  }, [selectedAgentValue]);
  
  // Separate effect to fetch when selection/auth changes (always refetch)
  useEffect(() => {
    if (session?.accessToken) {
      const agentFilter = selectedAgentValue === "all" ? undefined : selectedAgentValue;
      // When toggling filters, carry forward the latest threads version to avoid stale results across filters
      fetchThreads(agentFilter, false, latestThreadsVersionRef.current);
    }
  }, [selectedAgentValue, session?.accessToken, fetchThreads]);

  // Handle agent filter change
  const handleAgentFilterChange = (value: string) => {
    setSelectedAgentValue(value);
    selectedAgentRef.current = value;
    setOffset(0);
    setHasMore(true);
    if (value === "all" && allThreadsCacheRef.current) {
      // Immediately show cached full list to avoid stale UI, then confirm with network
      setThreads(allThreadsCacheRef.current);
    }
    fetchThreads(value === "all" ? undefined : value, false, latestThreadsVersionRef.current);
    setFilterOpen(false);
  };

  // Get selected agent display name
  const getSelectedAgentDisplay = () => {
    if (selectedAgentValue === "all") {
      return "All Agents";
    }
    
    const [selectedAssistantId, selectedDeploymentId] = selectedAgentValue.split(":");
    const selectedAgent = agents.find(
      (item) =>
        item.assistant_id === selectedAssistantId &&
        item.deploymentId === selectedDeploymentId,
    );

    return selectedAgent ? selectedAgent.name : "Select agent...";
  };

  // Get name from agent value for search filtering
  const getNameFromValue = (value: string) => {
    if (value === "all") return "All Agents";
    
    const [selectedAssistantId, selectedDeploymentId] = value.split(":");
    const selectedAgent = agents.find(
      (item) =>
        item.assistant_id === selectedAssistantId &&
        item.deploymentId === selectedDeploymentId,
    );

    return selectedAgent ? selectedAgent.name : "";
  };

  // Load more threads
  const loadMoreThreads = () => {
    const agentFilter = selectedAgentValue === "all" ? undefined : selectedAgentValue;
    fetchThreads(agentFilter, true);
  };

  // Handle thread click with layered fallback
  const handleThreadClick = (thread: Thread) => {
    // Extract agent info from thread metadata
    const originalAgentId = thread.metadata?.assistant_id;
    if (!originalAgentId) {
      toast.error("Unable to determine agent for this thread");
      return;
    }

    // STEP 1: Try to find the original agent
    let selectedAgent = agents.find(a => a.assistant_id === originalAgentId);
    let _fallbackType: 'none' | 'same_graph' | 'primary' = 'none';

    if (selectedAgent) {
      // Original agent found - proceed normally
      router.push(`/?agentId=${originalAgentId}&deploymentId=${selectedAgent.deploymentId}&threadId=${thread.thread_id}`);
      return;
    }

    // STEP 2: Agent not found - try to find an agent with the same graph_id
    // First, we need to find what graph the original thread was using
    // We'll try to infer this from other agents or use a fallback approach
    
    // Try to find agents with the same graph_id (if we had stored it)
    // Since we don't have graph_id in thread metadata, we'll skip this for now
    // and go straight to primary fallback

    // STEP 3: Fall back to primary agent
    const fallbackAgent = agents.find(isUserSpecifiedDefaultAgent) || agents.find(isPrimaryAssistant);
    
    if (fallbackAgent) {
      _fallbackType = 'primary';
      selectedAgent = fallbackAgent;
      
      // Show warning toast
      toast.warning("Original agent was deleted", {
        description: `Loading with ${selectedAgent.name} - conversation may not work as expected.`,
        duration: 5000,
      });
      
      // Navigate with fallback agent but keep original thread
      router.push(`/?agentId=${selectedAgent.assistant_id}&deploymentId=${selectedAgent.deploymentId}&threadId=${thread.thread_id}&agentMismatch=true`);
      return;
    }

    // STEP 4: No fallback available - show error
    toast.error("Unable to open thread", {
      description: "Original agent was deleted and no suitable replacement found. Please contact support.",
      duration: 7000,
    });
  };

  // Toggle group expansion
  const toggleGroup = (groupName: string) => {
    const newSet = new Set(expandedGroups);
    if (newSet.has(groupName)) {
      newSet.delete(groupName);
    } else {
      newSet.add(groupName);
    }
    setExpandedGroups(newSet);
  };

  // Handle thread deletion
  const handleDeleteThread = (thread: Thread) => {
    setThreadToDelete(thread);
    setDeleteDialogOpen(true);
  };

  const confirmDeleteThread = async () => {
    if (!threadToDelete) return;

    // Get the deployment ID for this thread
    const originalAgentId = threadToDelete.metadata?.assistant_id;
    const agent = agents.find(a => a.assistant_id === originalAgentId);
    const deploymentId = agent?.deploymentId || deployments[0]?.id;

    if (!deploymentId) {
      const message = threadMessages.delete.error("Unable to determine deployment for thread deletion");
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
      return;
    }

    const result = await deleteThread(threadToDelete.thread_id, deploymentId);
    
    if (result.ok) {
      // Remove thread from local state
      setThreads(prev => prev.filter(t => t.thread_id !== threadToDelete.thread_id));
      
      // Check if we need to navigate away from the current thread
      const currentUrl = new URL(window.location.href);
      const currentThreadId = currentUrl.searchParams.get('threadId');
      
      if (currentThreadId === threadToDelete.thread_id) {
        // Navigate to new thread (clear threadId)
        router.push('/');
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

  // Group threads by time
  const groupedThreads = useMemo(() => {
    return groupThreadsByTime(threads);
  }, [threads]);

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarMenu>
        {/* Main Chat History Navigation Item */}
        <SidebarMenuItem>
          <div className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm font-medium">
            <FileClock className="h-4 w-4" />
            <span>Chat History</span>
          </div>
        </SidebarMenuItem>

        {/* Agent Filter */}
        <SidebarMenuItem>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="w-full">
                <Popover open={filterOpen} onOpenChange={setFilterOpen}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      role="combobox"
                      aria-expanded={filterOpen}
                      className="h-8 w-full justify-between text-xs font-normal border-border bg-background text-foreground hover:bg-accent hover:text-foreground"
                    >
                      {getSelectedAgentDisplay()}
                      <ChevronDown className="h-4 w-4 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent
                    align="start"
                    className="w-full min-w-[180px] p-0 rounded-lg"
                  >
                    <Command
                      className="rounded-lg overflow-hidden [&_[data-slot=command-input-wrapper]]:rounded-t-lg [&_[data-slot=command-input-wrapper]]:border-b-0"
                      filter={(value: string, search: string) => {
                        const name = getNameFromValue(value);
                        if (!name) return 0;
                        if (name.toLowerCase().includes(search.toLowerCase())) {
                          return 1;
                        }
                        return 0;
                      }}
                    >
                      <CommandInput placeholder="Search agents..." className="border-none text-xs h-8" />
                      <CommandList className={cn("max-h-[250px]", ...getScrollbarClasses('y'))}>
                        <CommandEmpty className="text-xs py-4">No agents found.</CommandEmpty>
                        
                        {/* All Agents Option */}
                        <CommandItem
                          value="all"
                          onSelect={handleAgentFilterChange}
                          className="flex w-full items-center justify-between px-4 py-1.5 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer"
                        >
                          <div className="flex items-center gap-2 flex-1">
                            <Check
                              className={cn(
                                "h-3 w-3",
                                selectedAgentValue === "all" ? "opacity-100" : "opacity-0",
                              )}
                            />
                            <span className="flex-1 truncate text-xs font-medium">
                              All Agents
                            </span>
                          </div>
                        </CommandItem>
                        
                        {/* Group all agents by graph type across all deployments */}
                        {(() => {
                          // Get all agents and group by graph_id
                          const agentsGroupedByGraphs = groupAgentsByGraphs(agents);
                          
                          return agentsGroupedByGraphs.map((agentGroup) => {
                            if (agentGroup.length === 0) return null;
                            
                            const graphId = agentGroup[0].graph_id;
                            const sortedAgents = sortAgentGroup(agentGroup);
                            
                            return (
                              <React.Fragment key={graphId}>
                                {/* Graph Type Header */}
                                <div className="px-3 py-1.5 text-xs font-medium text-foreground">
                                  {graphNameById[graphId] || getGraphDisplayName(graphId)}
                                </div>
                              
                                {/* Agents in this group */}
                                {sortedAgents.map((item) => {
                                  const itemValue = `${item.assistant_id}:${item.deploymentId}`;
                                  const isSelected = selectedAgentValue === itemValue;
                                  const isDefault = isUserCreatedDefaultAssistant(item);
                                  const isPrimary = isPrimaryAssistant(item);

                                  return (
                                    <CommandItem
                                      key={itemValue}
                                      value={itemValue}
                                      onSelect={handleAgentFilterChange}
                                      className="flex w-full items-center justify-between px-4 py-1.5 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer"
                                    >
                                      <div className="flex items-center gap-2 flex-1">
                                        <Check
                                          className={cn(
                                            "h-3 w-3",
                                            isSelected ? "opacity-100" : "opacity-0",
                                          )}
                                        />
                                        
                                        <span className="flex-1 truncate text-xs">
                                          {item.name}
                                        </span>
                                      </div>
                                      
                                      <div className="flex items-center gap-1.5 flex-shrink-0">
                                        {isPrimary && (
                                          <Star className="h-3 w-3 text-yellow-500" />
                                        )}
                                        {isDefault && (
                                          <span className="text-[10px] text-muted-foreground">
                                            Default
                                          </span>
                                        )}
                                      </div>
                                    </CommandItem>
                                  );
                                })}
                              </React.Fragment>
                            );
                          });
                        })()}
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <p>Filter by agent</p>
            </TooltipContent>
          </Tooltip>
        </SidebarMenuItem>

        {/* Thread History */}
          {loading ? (
            <div className="space-y-2 px-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : groupedThreads.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-8 text-muted-foreground">
              <Clock className="h-8 w-8" />
              <p className="text-sm">No chat history found</p>
            </div>
          ) : (
            groupedThreads.map((group) => (
              <div key={group.name}>
                {/* Group Header */}
                <SidebarMenuItem>
                  <SidebarMenuButton
                    onClick={() => toggleGroup(group.name)}
                    className="w-full justify-between hover:bg-transparent"
                  >
                    <span className="text-xs font-medium text-muted-foreground">
                      {group.name}
                    </span>
                    {expandedGroups.has(group.name) ? (
                      <ChevronDown className="h-3 w-3" />
                    ) : (
                      <ChevronRight className="h-3 w-3" />
                    )}
                  </SidebarMenuButton>
                </SidebarMenuItem>

                {/* Group Threads */}
                {expandedGroups.has(group.name) && (
                  <div className="ml-3 space-y-1">
                    {group.threads.map((thread) => {
                      // Use mirror name first, then fallback to first human message, then "New chat"
                      const mirrorName = (thread as any).name;
                      const firstMessage = getFirstHumanMessageContent(thread);
                      const displayText = mirrorName || firstMessage || "New chat";
                      
                      return (
                        <SidebarMenuItem key={thread.thread_id}>
                          <div className="group flex w-full items-center justify-between">
                            {renamingThreadId === thread.thread_id ? (
                              <div className="flex w-full items-center gap-2 pl-2">
                                <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
                                <Input
                                  value={renameValue}
                                  onChange={(e) => setRenameValue(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                      confirmRename();
                                    } else if (e.key === 'Escape') {
                                      cancelRename();
                                    }
                                  }}
                                  onBlur={confirmRename}
                                  className="h-6 text-xs border-0 bg-transparent p-0 focus-visible:ring-1 focus-visible:ring-ring"
                                  autoFocus
                                  disabled={isRenaming}
                                />
                              </div>
                            ) : (
                              <SidebarMenuButton
                                onClick={() => handleThreadClick(thread)}
                                className="flex-1 justify-start pl-2 text-xs pr-1"
                                size="sm"
                              >
                                <div className="flex w-full items-center gap-2">
                                  <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50" />
                                  <span className="truncate text-xs">{displayText}</span>
                                </div>
                              </SidebarMenuButton>
                            )}
                            <ThreadActionMenu
                              onDelete={() => handleDeleteThread(thread)}
                              onRename={() => handleRenameThread(thread)}
                              disabled={isDeleting || isRenaming}
                            />
                          </div>
                        </SidebarMenuItem>
                      );
                    })}
                  </div>
                )}
              </div>
            ))
          )}
          
          {/* Load More Button */}
          {!loading && hasMore && threads.length > 0 && (
            <SidebarMenuItem>
              <Button
                variant="ghost"
                size="sm"
                onClick={loadMoreThreads}
                className="w-full justify-center text-xs text-muted-foreground hover:text-foreground"
                disabled={loading}
              >
                <Plus className="h-3 w-3 mr-2" />
                Load more
              </Button>
            </SidebarMenuItem>
          )}
      </SidebarMenu>

      {/* Thread Delete Confirmation Dialog */}
      <ThreadDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        onConfirm={confirmDeleteThread}
        isLoading={isDeleting}
      />
    </SidebarGroup>
  );
} 