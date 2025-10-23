"use client";

import React, { useState, useRef, useEffect } from "react";
import { Thread } from "./components/thread";
import { ConfigurationSidebar } from "./components/configuration-sidebar";
import { ThreadHistorySidebar } from "./components/thread-history-sidebar";
import { SidebarButtons } from "./components/sidebar-buttons";
import { cn } from "@/lib/utils";
import { useQueryState } from "nuqs";
import { useDefaultAgentSelection } from "@/hooks/use-default-agent-selection";
import { Button } from "@/components/ui/button";
import { AgentSelectionModal } from "@/components/ui/agent-selection-modal";
import { StreamProvider } from "@/features/chat/providers/Stream";

// Add a feature flag for the modal approach
const USE_AGENT_SELECTION_MODAL = process.env.NEXT_PUBLIC_USE_AGENT_SELECTION_MODAL === "true";

interface ChatInterfaceProps {
  headerIntegrated?: boolean;
  historyOpen?: boolean;
  setHistoryOpen?: (open: boolean) => void;
  configOpen?: boolean;
  setConfigOpen?: (open: boolean) => void;
}

/**
 * The parent component containing the chat interface.
 */
export default function ChatInterface({
  headerIntegrated = false,
  historyOpen: externalHistoryOpen,
  setHistoryOpen: externalSetHistoryOpen,
  configOpen: externalConfigOpen,
  setConfigOpen: externalSetConfigOpen,
}: ChatInterfaceProps = {}): React.ReactNode {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  // Use external state when header is integrated, otherwise use internal state
  const [internalHistoryOpen, setInternalHistoryOpen] = useState(false);
  const [internalConfigOpen, setInternalConfigOpen] = useState(false);
  const [showAgentModal, setShowAgentModal] = useState(false);

  const historyOpen = headerIntegrated ? (externalHistoryOpen ?? false) : internalHistoryOpen;
  const setHistoryOpen = headerIntegrated ? (externalSetHistoryOpen ?? setInternalHistoryOpen) : setInternalHistoryOpen;
  const configOpen = headerIntegrated ? (externalConfigOpen ?? false) : internalConfigOpen;
  const setConfigOpen = headerIntegrated ? (externalSetConfigOpen ?? setInternalConfigOpen) : setInternalConfigOpen;
  
  // Get agentId from URL parameters for StreamDual
  const [agentId, setAgentId] = useQueryState("agentId");
  const [_deploymentId, setDeploymentId] = useQueryState("deploymentId");
  
  // Ensure default agent is selected if no agentId is present
  const defaultAgentSelection = useDefaultAgentSelection();

  const historyRef = useRef<HTMLDivElement>(null);
  const configRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLDivElement>(null);

  // Handler for agent selection from modal
  const handleAgentSelect = (selectedAgentId: string, selectedDeploymentId: string) => {
    setAgentId(selectedAgentId);
    setDeploymentId(selectedDeploymentId);
    setShowAgentModal(false);
  };

  // Show modal when using modal approach and no agent is selected
  useEffect(() => {
    if (USE_AGENT_SELECTION_MODAL && !agentId && !defaultAgentSelection.isLoading && !defaultAgentSelection.isAuthLoading) {
      setShowAgentModal(true);
    }
  }, [agentId, defaultAgentSelection.isLoading, defaultAgentSelection.isAuthLoading]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;

      // Check if the click is on a portal element (dialog, select menu, etc.)
      // Common portal containers have these class names or data attributes
      const isPortalElement =
        document.querySelector('[role="dialog"]')?.contains(target) ||
        document.querySelector('[role="listbox"]')?.contains(target) ||
        document.querySelector(".cm-tooltip")?.contains(target) ||
        document.querySelector(".popover")?.contains(target) ||
        document.querySelector(".dropdown")?.contains(target) ||
        document
          .querySelector("[data-radix-popper-content-wrapper]")
          ?.contains(target) ||
        // Alert components
        document.querySelector('[role="alertdialog"]')?.contains(target) ||
        document.querySelector(".alert")?.contains(target) ||
        document.querySelector(".alert-dialog")?.contains(target) ||
        document.querySelector(".alert-dialog-content")?.contains(target) ||
        Array.from(document.querySelectorAll('[class*="alert"]')).some((el) =>
          el.contains(target),
        );

      // If the click is on a portal element, don't close the sidebar
      if (isPortalElement) {
        return;
      }

      // Check if the click is on header buttons when header is integrated
      const headerButtons = headerIntegrated ? document.getElementById("chat-header-buttons") : null;
      const isHeaderButtonClick = headerButtons?.contains(target);

      // Check if history sidebar is open and the click is outside of it and the buttons
      if (
        historyOpen &&
        historyRef.current &&
        !historyRef.current.contains(target) &&
        !isHeaderButtonClick &&
        (!buttonRef.current || !buttonRef.current.contains(target))
      ) {
        setHistoryOpen(false);
      }

      // Check if config sidebar is open and the click is outside of it and the buttons
      if (
        configOpen &&
        configRef.current &&
        !configRef.current.contains(target) &&
        !isHeaderButtonClick &&
        (!buttonRef.current || !buttonRef.current.contains(target))
      ) {
        setConfigOpen(false);
      }
    }

    // Add event listener
    document.addEventListener("mousedown", handleClickOutside);

    // Clean up
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [historyOpen, configOpen, headerIntegrated, setHistoryOpen, setConfigOpen]);

  // Always render the same outer layout to avoid hydration mismatches.
  // Swap only the inner content depending on agent state.
  return (
    <>
      <AgentSelectionModal
        open={showAgentModal}
        onAgentSelect={handleAgentSelect}
        onClose={() => setShowAgentModal(false)}
      />
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div
          className={cn(
            "flex flex-1 flex-col min-h-0 overflow-hidden",
            historyOpen || configOpen ? "md:mr-[36rem]" : ""
          )}
        >
          {!mounted ? (
            <div className="flex h-full w-full items-center justify-center">
              <div className="animate-in fade-in-0 zoom-in-95 bg-background flex min-h-32 max-w-md flex-col items-center justify-center rounded-lg border p-6 shadow-lg">
                <div className="flex items-center gap-3">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
                  <span className="text-sm text-muted-foreground">Loading…</span>
                </div>
              </div>
            </div>
          ) : agentId ? (
            <StreamProvider>
              <Thread
                historyOpen={historyOpen}
                configOpen={configOpen}
              />
            </StreamProvider>
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              {defaultAgentSelection.isLoading || defaultAgentSelection.isAuthLoading ? (
                <div className="animate-in fade-in-0 zoom-in-95 bg-background flex min-h-32 max-w-md flex-col items-center justify-center rounded-lg border p-6 shadow-lg">
                  <div className="flex items-center gap-3">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
                    <span className="text-sm text-muted-foreground">
                      {defaultAgentSelection.isAuthLoading ? "Initialising authentication..." : "Loading agents..."}
                    </span>
                  </div>
                </div>
              ) : defaultAgentSelection.error ? (
                <div className="text-center max-w-md mx-auto">
                  <h2 className="text-lg font-semibold mb-2">Unable to Load Agents</h2>
                  <p className="text-muted-foreground mb-4">Error: {defaultAgentSelection.error}</p>
                  <Button onClick={defaultAgentSelection.retry} variant="outline" className="mb-4">
                    Try Again
                  </Button>
                </div>
              ) : (
                <div className="text-center max-w-md mx-auto">
                  <h2 className="text-lg font-semibold mb-2">No Agents Available</h2>
                  <p className="text-muted-foreground mb-4">
                    No agents are available for your account.<br />
                    Please contact your administrator or check your notifications for pending invitations.
                  </p>
                  <div className="space-y-2">
                    <Button onClick={() => (window.location.href = '/agents')} variant="default">
                      View All Agents
                    </Button>
                    <p className="text-xs text-muted-foreground">Or try refreshing the page</p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        {!headerIntegrated && (
          <SidebarButtons
            ref={buttonRef}
            historyOpen={historyOpen}
            setHistoryOpen={setHistoryOpen}
            configOpen={configOpen}
            setConfigOpen={setConfigOpen}
          />
        )}
        <ThreadHistorySidebar ref={historyRef} open={historyOpen} setOpen={setHistoryOpen} />
        <ConfigurationSidebar ref={configRef} open={configOpen} setOpen={setConfigOpen} />
      </div>
    </>
  );
}
