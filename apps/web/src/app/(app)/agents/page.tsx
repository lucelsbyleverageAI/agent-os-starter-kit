"use client";

import AgentsInterface from "@/features/agents";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Layers } from "lucide-react";
import { AdminInitializeButton } from "@/features/agents/components/admin-initialize-button";
import { ViewTemplatesDialog } from "@/features/agents/components/view-templates-dialog";
import { useUserRole } from "@/providers/UserRole";
import { useAgentsContext } from "@/providers/Agents";

import React, { useState } from "react";
import { AppHeader } from "@/components/app-header";

/**
 * The /agents page.
 * Contains the list of all agents the user has access to.
 */
export default function AgentsPage(): React.ReactNode {
  const [showViewTemplatesDialog, setShowViewTemplatesDialog] = useState(false);
  const { isDevAdmin } = useUserRole();
  const { discoveryData } = useAgentsContext();

  return (
    <React.Suspense fallback={<div>Loading (layout)...</div>}>
      <AppHeader
        actions={
          <div className="flex items-center gap-2">
            <Button
              onClick={() => setShowViewTemplatesDialog(true)}
              size="sm"
              variant="outline"
            >
              <Layers className="mr-2 h-4 w-4" />
              View Agent Templates
            </Button>
            {isDevAdmin && <AdminInitializeButton size="sm" />}
          </div>
        }
      >
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>Agents</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>
      <AgentsInterface />

      <ViewTemplatesDialog
        open={showViewTemplatesDialog}
        onOpenChange={setShowViewTemplatesDialog}
        graphs={discoveryData?.valid_graphs || []}
        userIsDevAdmin={isDevAdmin}
      />
    </React.Suspense>
  );
}
