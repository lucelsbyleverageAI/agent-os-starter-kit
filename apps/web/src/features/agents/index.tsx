"use client";

import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { AgentMarketplace } from "./components/agent-marketplace";
import { CreateAgentDialog } from "./components/create-edit-agent-dialogs/create-agent-dialog";

export default function AgentsInterfaceV2() {
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  return (
    <div className="container mx-auto px-4 md:px-8 lg:px-12 py-3">
      {/* Hero Section */}
      <div className="flex flex-col items-center justify-center text-center space-y-4 mb-6">
        <div className="space-y-2">
          <h1 className="text-5xl font-bold tracking-tight">Agents</h1>
          <p className="text-muted-foreground text-xl">
            Browse and manage your agents
          </p>
        </div>
        <Button
          onClick={() => setShowCreateDialog(true)}
          size="lg"
          className="text-base px-6 py-6"
        >
          <Plus className="mr-2 h-5 w-5" />
          Create New Agent
        </Button>
      </div>

      {/* Agent Marketplace */}
      <div className="mt-6">
        <Suspense fallback={<p>Loading agents...</p>}>
          <AgentMarketplace onCreateAgent={() => setShowCreateDialog(true)} />
        </Suspense>
      </div>

      <CreateAgentDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
      />
    </div>
  );
}
