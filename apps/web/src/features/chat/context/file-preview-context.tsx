"use client";

import React, { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from "react";

// Types
export interface FilePreviewFile {
  display_name: string;
  filename: string;
  file_type: string;
  mime_type: string;
  storage_path: string;
  file_size: number;
  description?: string;
}

interface FilePreviewContextValue {
  file: FilePreviewFile | null;
  isOpen: boolean;
  openPreview: (file: FilePreviewFile) => void;
  closePreview: () => void;
}

const FilePreviewContext = createContext<FilePreviewContextValue | null>(null);

interface FilePreviewProviderProps {
  children: ReactNode;
  threadId?: string | null;
}

export function FilePreviewProvider({ children, threadId }: FilePreviewProviderProps) {
  const [file, setFile] = useState<FilePreviewFile | null>(null);
  const prevThreadIdRef = useRef<string | null | undefined>(threadId);

  const openPreview = useCallback((newFile: FilePreviewFile) => {
    setFile(newFile);
  }, []);

  const closePreview = useCallback(() => {
    setFile(null);
  }, []);

  // Close preview when threadId changes (user navigates to new/different thread)
  useEffect(() => {
    if (prevThreadIdRef.current !== threadId) {
      setFile(null);
      prevThreadIdRef.current = threadId;
    }
  }, [threadId]);

  const value: FilePreviewContextValue = {
    file,
    isOpen: file !== null,
    openPreview,
    closePreview,
  };

  return (
    <FilePreviewContext.Provider value={value}>
      {children}
    </FilePreviewContext.Provider>
  );
}

export function useFilePreview() {
  const context = useContext(FilePreviewContext);
  if (!context) {
    throw new Error("useFilePreview must be used within a FilePreviewProvider");
  }
  return context;
}

// Optional hook that doesn't throw - useful for components that may be outside the provider
export function useFilePreviewOptional() {
  return useContext(FilePreviewContext);
}
