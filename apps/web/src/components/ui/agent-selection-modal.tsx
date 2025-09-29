"use client";

import React, { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AgentsCombobox } from "@/components/ui/agents-combobox";
import { useAgentsContext } from "@/providers/Agents";
import { Loader2, MessageCircle } from "lucide-react";
import Image from "next/image";

interface AgentSelectionModalProps {
  open: boolean;
  onAgentSelect: (agentId: string, deploymentId: string) => void;
  onClose?: () => void;
}

export function AgentSelectionModal({ 
  open, 
  onAgentSelect, 
  onClose 
}: AgentSelectionModalProps) {
  const { agents, loading } = useAgentsContext();
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [comboboxOpen, setComboboxOpen] = useState(false);

  const handleStartChat = () => {
    if (!selectedAgent) return;
    
    const [agentId, deploymentId] = selectedAgent.split(":");
    onAgentSelect(agentId, deploymentId);
  };

  const handleAgentChange = (value: string | string[] | undefined) => {
    const nextValue = Array.isArray(value) ? value[0] : value;
    setSelectedAgent(nextValue || "");
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader className="text-center">
          <div className="flex justify-center mb-4">
            <Image 
              src="/logo_icon_round.png" 
              alt="AgentOS Logo" 
              width={48} 
              height={48} 
            />
          </div>
          <DialogTitle className="text-xl">Welcome to AgentOS</DialogTitle>
          <DialogDescription>
            Select an agent to start a new conversation
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin mr-2" />
              <span className="text-sm text-muted-foreground">Loading agents...</span>
            </div>
          ) : agents.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-muted-foreground mb-4">
                No agents are currently available.
              </p>
              <Button 
                variant="outline" 
                onClick={() => window.location.href = '/agents'}
              >
                Manage Agents
              </Button>
            </div>
          ) : (
            <>
              <AgentsCombobox
                agents={agents}
                agentsLoading={loading}
                value={selectedAgent}
                setValue={handleAgentChange}
                open={comboboxOpen}
                setOpen={setComboboxOpen}
                placeholder="Choose an agent to chat with..."
                showBorder={true}
                className="w-full"
              />
              
              <Button 
                onClick={handleStartChat}
                disabled={!selectedAgent}
                className="w-full"
                size="lg"
              >
                <MessageCircle className="mr-2 h-4 w-4" />
                Start Chat
              </Button>
            </>
          )}
        </div>
        
        <div className="text-center text-xs text-muted-foreground">
          You can change agents later from the sidebar
        </div>
      </DialogContent>
    </Dialog>
  );
} 