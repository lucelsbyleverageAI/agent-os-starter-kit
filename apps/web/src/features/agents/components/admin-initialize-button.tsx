"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Eye, Play, Loader2, RefreshCw } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAdminPlatform } from "@/hooks/use-admin-platform";
import { useAgentsContext } from "@/providers/Agents";
import { notify } from "@/utils/toast";
import { adminMessages } from "@/utils/toast-messages";

interface AdminInitializeButtonProps {
  size?: "default" | "sm" | "lg" | "icon";
}

export function AdminInitializeButton({ size = "default" }: AdminInitializeButtonProps) {
  const { loading, initializePlatform, previewInitialization, isDevAdmin } = useAdminPlatform();
  const { refreshAgents } = useAgentsContext();
  const [showDropdown, setShowDropdown] = useState(false);

  if (!isDevAdmin) {
    return null;
  }

  const handlePreview = async () => {
    setShowDropdown(false);
    const result = await previewInitialization();
    if (result.ok) {
      const message = adminMessages.initialize.preview(result.data!.total_operations, result.data!.operations_performed.length);
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });
    } else {
      if (result.errorCode === "PERMISSION_DENIED") {
        const message = adminMessages.permissionDenied();
        notify.error(message.title, {
          description: message.description,
          key: message.key,
        });
      } else {
        const message = adminMessages.initialize.error(result.errorMessage);
        notify.error(message.title, {
          description: message.description,
          key: message.key,
        });
      }
    }
  };

  const handleInitialize = async () => {
    setShowDropdown(false);
    const result = await initializePlatform(false);
    if (result.ok) {
      const message = adminMessages.initialize.success(result.data!.total_operations, result.data!.duration_ms);
      notify.success(message.title, {
        description: message.description,
        key: message.key,
      });
      
      // Refresh agents after successful initialization - silent since user already got success toast
      await refreshAgents(true);
    } else {
      if (result.errorCode === "PERMISSION_DENIED") {
        const message = adminMessages.permissionDenied();
        notify.error(message.title, {
          description: message.description,
          key: message.key,
        });
      } else {
        const message = adminMessages.initialize.error(result.errorMessage);
        notify.error(message.title, {
          description: message.description,
          key: message.key,
        });
      }
    }
  };

  return (
    <TooltipProvider>
      <Tooltip>
        <DropdownMenu open={showDropdown} onOpenChange={setShowDropdown}>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size={size} disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Force LangGraph Discovery
                  </>
                )}
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuItem onClick={handlePreview} disabled={loading}>
              <Eye className="mr-2 h-4 w-4" />
              Preview Changes
              <span className="text-xs text-muted-foreground ml-auto">Dry Run</span>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleInitialize} disabled={loading}>
              <Play className="mr-2 h-4 w-4" />
              Force Discovery Now
              <span className="text-xs text-muted-foreground ml-auto">Live</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <TooltipContent side="bottom" className="max-w-xs">
          <p className="text-sm">
            Retrieves the latest graphs (agent templates) from LangGraph and grants permissions to dev admins. 
            Use this after deploying new graphs that need immediate access.
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
} 