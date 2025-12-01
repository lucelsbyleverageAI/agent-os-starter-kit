"use client";

import React, { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from "react";

// Types
export interface SubAgentPreviewData {
  subagentType: string;      // e.g., "general-purpose", "custom-agent"
  taskDescription: string;   // The task that was delegated
  response: string;          // Markdown response from sub-agent
  toolCallId: string;        // For unique identification
}

interface SubAgentPreviewContextValue {
  preview: SubAgentPreviewData | null;
  isOpen: boolean;
  openPreview: (data: SubAgentPreviewData) => void;
  closePreview: () => void;
}

const SubAgentPreviewContext = createContext<SubAgentPreviewContextValue | null>(null);

interface SubAgentPreviewProviderProps {
  children: ReactNode;
  threadId?: string | null;
}

export function SubAgentPreviewProvider({ children, threadId }: SubAgentPreviewProviderProps) {
  const [preview, setPreview] = useState<SubAgentPreviewData | null>(null);
  const prevThreadIdRef = useRef<string | null | undefined>(threadId);

  const openPreview = useCallback((data: SubAgentPreviewData) => {
    setPreview(data);
  }, []);

  const closePreview = useCallback(() => {
    setPreview(null);
  }, []);

  // Close preview when threadId changes (user navigates to new/different thread)
  useEffect(() => {
    if (prevThreadIdRef.current !== threadId) {
      setPreview(null);
      prevThreadIdRef.current = threadId;
    }
  }, [threadId]);

  const value: SubAgentPreviewContextValue = {
    preview,
    isOpen: preview !== null,
    openPreview,
    closePreview,
  };

  return (
    <SubAgentPreviewContext.Provider value={value}>
      {children}
    </SubAgentPreviewContext.Provider>
  );
}

export function useSubAgentPreview() {
  const context = useContext(SubAgentPreviewContext);
  if (!context) {
    throw new Error("useSubAgentPreview must be used within a SubAgentPreviewProvider");
  }
  return context;
}

// Optional hook that doesn't throw - useful for components that may be outside the provider
export function useSubAgentPreviewOptional() {
  return useContext(SubAgentPreviewContext);
}
