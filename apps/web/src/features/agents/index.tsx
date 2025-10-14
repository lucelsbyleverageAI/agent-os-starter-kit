"use client";

import { Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { Plus, Layers } from "lucide-react";
import { AgentMarketplace } from "./components/agent-marketplace";
import { CreateAgentDialog } from "./components/create-edit-agent-dialogs/create-agent-dialog";
import { AdminInitializeButton } from "./components/admin-initialize-button";
import { ViewTemplatesDialog } from "./components/view-templates-dialog";
import { useUserRole } from "@/providers/UserRole";
import { useAgentsContext } from "@/providers/Agents";

export default function AgentsInterfaceV2() {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showViewTemplatesDialog, setShowViewTemplatesDialog] = useState(false);
  const { isDevAdmin } = useUserRole();
  const { discoveryData } = useAgentsContext();

  return (
    <div className="container mx-auto px-4 py-6">
      {/* Admin Actions - Top Right */}
      <div className="flex items-center justify-end gap-2 mb-8">
        <Button
          onClick={() => setShowViewTemplatesDialog(true)}
          size="lg"
          variant="outline"
        >
          <Layers className="mr-2 h-4 w-4" />
          View Agent Templates
        </Button>
        {isDevAdmin && <AdminInitializeButton size="lg" />}
      </div>

      {/* Hero Section */}
      <div className="flex flex-col items-center justify-center text-center space-y-6 mb-12">
        <div className="space-y-3">
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
      <div className="mt-8">
        <Suspense fallback={<p>Loading agents...</p>}>
          <AgentMarketplace onCreateAgent={() => setShowCreateDialog(true)} />
        </Suspense>
      </div>

      <CreateAgentDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
      />

      <ViewTemplatesDialog
        open={showViewTemplatesDialog}
        onOpenChange={setShowViewTemplatesDialog}
        graphs={discoveryData?.valid_graphs || []}
        userIsDevAdmin={isDevAdmin}
      />
    </div>
  );
}
