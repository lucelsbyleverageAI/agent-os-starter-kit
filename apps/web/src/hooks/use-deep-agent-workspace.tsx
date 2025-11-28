"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useStreamContext } from "@/features/chat/providers/Stream";
import { useAgentsContext } from "@/providers/Agents";
import { useAuthContext } from "@/providers/Auth";
import { useQueryState } from "nuqs";
import { TodoItem, DeepAgentWorkspaceData } from "@/types/deep-agent";
import {
  isDeepAgentSchema,
  extractDeepAgentWorkspaceData,
  hasDeepAgentWorkspaceData
} from "@/lib/deep-agent-utils";

// Helper to get localStorage key for sidebar state
function getStorageKey(threadId: string | null): string {
  return `workspace-sidebar-${threadId || 'default'}`;
}

export function useDeepAgentWorkspace() {
  const [agentId] = useQueryState("agentId");
  const [threadId] = useQueryState("threadId");
  const { agents } = useAgentsContext();
  const { session } = useAuthContext();
  const stream = useStreamContext();


  const [workspaceData, setWorkspaceData] = useState<DeepAgentWorkspaceData>({
    todos: [],
    files: {},
    publishedFiles: []
  });
  const [isDeepAgent, setIsDeepAgent] = useState(false);

  // Initialize sidebar collapsed state from localStorage (per thread)
  const [workspaceSidebarCollapsed, setWorkspaceSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return true;
    const storageKey = getStorageKey(threadId);
    const saved = localStorage.getItem(storageKey);
    return saved !== null ? JSON.parse(saved) : true;
  });

  // Find current agent and check if it's a deep agent
  const currentAgent = agents.find(a => a.assistant_id === agentId);
  
  

  // Check if current agent is a deep agent based on schema
  useEffect(() => {
    const checkDeepAgentSchema = async () => {
      if (!currentAgent?.assistant_id) {
        setIsDeepAgent(false);
        return;
      }
      try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (session?.accessToken) {
          headers.Authorization = `Bearer ${session.accessToken}`;
        }
        const response = await fetch(`/api/langconnect/agents/mirror/assistants/${currentAgent.assistant_id}/schemas`, { headers });
        if (response.ok) {
          const schemaData = await response.json();
          const isDeep = isDeepAgentSchema(schemaData?.state_schema);
          setIsDeepAgent(isDeep);
        } else {
          setIsDeepAgent(false);
        }
      } catch {
        setIsDeepAgent(false);
      }
    };

    if (currentAgent?.assistant_id) {
      checkDeepAgentSchema();
    } else {
      setIsDeepAgent(false);
    }
  }, [currentAgent?.assistant_id, session?.accessToken]);

  // Persist sidebar state to localStorage when it changes
  useEffect(() => {
    if (threadId) {
      const storageKey = getStorageKey(threadId);
      localStorage.setItem(storageKey, JSON.stringify(workspaceSidebarCollapsed));
    }
  }, [workspaceSidebarCollapsed, threadId]);

  // Reset workspace data when agent or thread changes
  useEffect(() => {
    setWorkspaceData({ todos: [], files: {}, publishedFiles: [] });
    // Default to not deep until proven otherwise for the new context
    setIsDeepAgent(false);
    // Load sidebar state from localStorage for the new thread
    if (typeof window !== 'undefined' && threadId) {
      const storageKey = getStorageKey(threadId);
      const saved = localStorage.getItem(storageKey);
      setWorkspaceSidebarCollapsed(saved !== null ? JSON.parse(saved) : true);
    } else {
      setWorkspaceSidebarCollapsed(true);
    }
  }, [agentId, threadId]);

  // Load and update state from stream.values
  useEffect(() => {
    if (stream.values && hasDeepAgentWorkspaceData(stream.values)) {

      if (!isDeepAgent) {

        setIsDeepAgent(true);
      }

      const { todos, files, publishedFiles } = extractDeepAgentWorkspaceData(stream.values);


      setWorkspaceData(prev => {
        // Merge todos (keep unique by content)
        const existingTodoContents = new Set(prev.todos.map(t => t.content));
        const newTodos = todos.filter((t: TodoItem) => !existingTodoContents.has(t.content));
        const updatedTodos = [...prev.todos, ...newTodos];

        // Update existing todos status if they match by content
        const finalTodos = updatedTodos.map(existingTodo => {
          const updatedTodo = todos.find((t: TodoItem) => t.content === existingTodo.content);
          return updatedTodo || existingTodo;
        });

        // Merge files (simple override)
        const updatedFiles = { ...prev.files, ...files };

        // Published files replace entirely (reducer on backend handles dedup by display_name)
        const finalPublishedFiles = publishedFiles.length > 0 ? publishedFiles : prev.publishedFiles;

        return {
          todos: finalTodos,
          files: updatedFiles,
          publishedFiles: finalPublishedFiles
        };
      });

      // Note: We no longer auto-expand the sidebar - user must click to open
    } else if (stream.values) {
      // If the new thread has no deep agent data, clear previous workspace state
      setWorkspaceData({ todos: [], files: {}, publishedFiles: [] });
      // Ensure we hide the workspace when no deep data is detected in the new context
      if (isDeepAgent) {
        setIsDeepAgent(false);
      }
      // Keep sidebar collapsed when empty
    }
  }, [stream.values, isDeepAgent]);

  const toggleWorkspaceSidebar = useCallback(() => {
    setWorkspaceSidebarCollapsed((prev: boolean) => !prev);
  }, []);

  return {
    isDeepAgent,
    workspaceData,
    workspaceSidebarCollapsed,
    toggleWorkspaceSidebar,
    hasWorkspaceData: workspaceData.todos.length > 0 || Object.keys(workspaceData.files).length > 0 || workspaceData.publishedFiles.length > 0
  };
}
