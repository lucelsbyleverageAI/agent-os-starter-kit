"use client";

import ChatInterface from "@/features/chat";
import React, { useState } from "react";
import { ChatHeader } from "@/features/chat/components/chat-header";
import { ThreadsProvider } from "@/providers/Thread";

export default function Home() {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);

  return (
    <>
      <ChatHeader
        historyOpen={historyOpen}
        setHistoryOpen={setHistoryOpen}
        configOpen={configOpen}
        setConfigOpen={setConfigOpen}
      />
      <ThreadsProvider>
        <ChatInterface
          headerIntegrated={true}
          historyOpen={historyOpen}
          setHistoryOpen={setHistoryOpen}
          configOpen={configOpen}
          setConfigOpen={setConfigOpen}
        />
      </ThreadsProvider>
    </>
  );
}