import type React from "react";
import { Button } from "@/components/ui/button";
import { PlusCircle } from "lucide-react";
import { CreateAgentDialog } from "./create-edit-agent-dialogs/create-agent-dialog";
import { AdminInitializeButton } from "./admin-initialize-button";
import { useUserRole } from "@/providers/UserRole";
import { useState } from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function PageHeader({ title, description, action }: PageHeaderProps) {
  const [showCreateAgentDialog, setShowCreateAgentDialog] = useState(false);
  const { isDevAdmin } = useUserRole();
  
  return (
    <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {description && (
          <p className="text-muted-foreground mt-1">{description}</p>
        )}
      </div>
      {action || (
        <div className="flex items-center gap-2">
          {isDevAdmin && <AdminInitializeButton />}
          <Button onClick={() => setShowCreateAgentDialog(true)}>
            <PlusCircle className="mr-2 h-4 w-4" />
            Create Agent
          </Button>
        </div>
      )}

      <CreateAgentDialog
        open={showCreateAgentDialog}
        onOpenChange={setShowCreateAgentDialog}
      />
    </div>
  );
}
