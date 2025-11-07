"use client";

import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Eye, Play, Loader2, RefreshCw, Upload } from "lucide-react";
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
  const { loading, initializePlatform, previewInitialization, reverseSyncAssistants, isDevAdmin } = useAdminPlatform();
  const { refreshAgents } = useAgentsContext();
  const [showDropdown, setShowDropdown] = useState(false);

  // Detect if running on localhost for local development features
  const isLocalhost = useMemo(() => {
    if (typeof window === 'undefined') return false;
    const apiUrl = process.env.NEXT_PUBLIC_LANGGRAPH_API_URL || '';
    return apiUrl.includes('localhost') || apiUrl.includes('127.0.0.1');
  }, []);

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

  const handleReverseSync = async () => {
    setShowDropdown(false);

    // Confirm with user before proceeding
    const confirmed = window.confirm(
      "This will recreate all assistants in LangGraph. Assistant IDs will change but threads and permissions will be preserved. Continue?"
    );

    if (!confirmed) {
      return;
    }

    const result = await reverseSyncAssistants();
    if (result.ok) {
      const { total, recreated, failed, duration_ms } = result.data!;

      if (failed === 0) {
        const message = adminMessages.reverseSync.success(total, recreated, duration_ms);
        notify.success(message.title, {
          description: message.description,
          key: message.key,
        });
      } else {
        const message = adminMessages.reverseSync.partial(total, recreated, failed);
        notify.warning(message.title, {
          description: message.description,
          key: message.key,
        });
      }

      // Refresh agents after successful sync - silent since user already got success toast
      await refreshAgents(true);
    } else {
      if (result.errorCode === "PERMISSION_DENIED") {
        const message = adminMessages.permissionDenied();
        notify.error(message.title, {
          description: message.description,
          key: message.key,
        });
      } else {
        const message = adminMessages.reverseSync.error(result.errorMessage);
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
            {isLocalhost && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleReverseSync} disabled={loading}>
                  <Upload className="mr-2 h-4 w-4" />
                  Reverse Sync to LangGraph
                  <span className="text-xs text-muted-foreground ml-auto">Local Only</span>
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
        <TooltipContent side="bottom" className="max-w-xs">
          <p className="text-sm">
            Retrieves the latest graphs (agent templates) from LangGraph and grants permissions to dev admins.
            Use this after deploying new graphs that need immediate access.
            {isLocalhost && " In local development, you can also reverse sync to recreate assistants in LangGraph."}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
} 