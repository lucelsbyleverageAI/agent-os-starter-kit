"use client";

import React from "react";
import { Settings, History } from "lucide-react";
import { AppHeader } from "@/components/app-header";
import { MinimalistIconButton } from "@/components/ui/minimalist-icon-button";
import { ChatBreadcrumb } from "@/features/chat/components/chat-breadcrumb";

interface ChatHeaderProps {
  historyOpen: boolean;
  setHistoryOpen: (open: boolean) => void;
  configOpen: boolean;
  setConfigOpen: (open: boolean) => void;
}

export function ChatHeader({ historyOpen, setHistoryOpen, configOpen, setConfigOpen }: ChatHeaderProps) {
  const handleConfigClick = () => {
    if (configOpen) {
      setConfigOpen(false);
    } else {
      setConfigOpen(true);
      setHistoryOpen(false);
    }
  };

  const handleHistoryClick = () => {
    if (historyOpen) {
      setHistoryOpen(false);
    } else {
      setHistoryOpen(true);
      setConfigOpen(false);
    }
  };

  const actions = (
    <div className="flex items-center gap-2" id="chat-header-buttons">
      <MinimalistIconButton
        icon={Settings}
        tooltip={configOpen ? "Close Configuration" : "Agent Configuration"}
        onClick={handleConfigClick}
        className={`h-8 w-8 ${configOpen ? 'bg-muted text-foreground' : ''}`}
      />
      <MinimalistIconButton
        icon={History}
        tooltip={historyOpen ? "Close History" : "History"}
        onClick={handleHistoryClick}
        className={`h-8 w-8 ${historyOpen ? 'bg-muted text-foreground' : ''}`}
      />
    </div>
  );

  return (
    <AppHeader actions={actions}>
      <ChatBreadcrumb />
    </AppHeader>
  );
} 