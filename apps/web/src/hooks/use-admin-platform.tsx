"use client";

import { useState } from "react";
import { useAuthContext } from "@/providers/Auth";
import { useAgentsContext } from "@/providers/Agents";
import { useUserRole } from "@/providers/UserRole";

// Result types for consistent error handling
interface SuccessResult<T = void> {
  ok: true;
  data?: T;
}

interface ErrorResult {
  ok: false;
  errorCode: string;
  errorMessage: string;
}

type Result<T = void> = SuccessResult<T> | ErrorResult;

interface AdminInitializePlatformRequest {
  dry_run?: boolean;
  target_user_id?: string;
  reason?: string;
}

interface EnhancementResult {
  operation: string;
  success: boolean;
  total_enhanced: number;
  failed: number;
  message: string;
  errors: string[];
}

interface AdminInitializePlatformResponse {
  dry_run: boolean;
  operations_performed: EnhancementResult[];
  total_operations: number;
  successful_operations: number;
  failed_operations: number;
  duration_ms: number;
  warnings: string[];
  summary: string;
}

interface ReverseSyncAssistantsResponse {
  total: number;
  recreated: number;
  failed: number;
  failed_assistants: Array<{
    name: string;
    old_id: string;
    error: string;
  }>;
  duration_ms: number;
  summary: string;
}

/**
 * Hook for admin platform initialization operations (dev admin only)
 */
export function useAdminPlatform() {
  const { session } = useAuthContext();
  const { isDevAdmin } = useUserRole();
  const [loading, setLoading] = useState(false);
  const {
    invalidateGraphDiscoveryCache,
    invalidateAssistantListCache,
    invalidateAllAssistantCaches,
    refreshAgents,
  } = useAgentsContext();

  /**
   * Initialize platform with all enhancement scenarios
   */
  const initializePlatform = async (dryRun: boolean = false): Promise<Result<AdminInitializePlatformResponse>> => {
    if (!isDevAdmin) {
      return {
        ok: false,
        errorCode: "PERMISSION_DENIED",
        errorMessage: "Only dev admins can initialize the platform",
      };
    }

    if (!session?.accessToken) {
      return {
        ok: false,
        errorCode: "NO_ACCESS_TOKEN",
        errorMessage: "No access token found",
      };
    }

    setLoading(true);
    try {
      const payload: AdminInitializePlatformRequest = {
        dry_run: dryRun
      };

      const response = await fetch(`/api/langconnect/agents/admin/initialize-platform`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.accessToken}`,
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errorText = await response.text();
        return {
          ok: false,
          errorCode: "INITIALIZATION_FAILED",
          errorMessage: `Failed to initialize platform: ${response.status} ${errorText}`,
        };
      }

      const result: AdminInitializePlatformResponse = await response.json();
      
      if (!dryRun) {
        // Invalidate all relevant caches and refresh UI immediately
        try {
          invalidateGraphDiscoveryCache();
          invalidateAssistantListCache();
          invalidateAllAssistantCaches();

          // Give the backend a brief moment to bump versions and finish sync, then refresh
          setTimeout(() => {
            refreshAgents(true);
          }, 200);
        } catch (_) {
          // No-op: cache invalidation is best-effort
        }
      }

      return {
        ok: true,
        data: result,
      };

    } catch (error) {
      console.error("Error initializing platform:", error);
      
      return {
        ok: false,
        errorCode: "INITIALIZATION_ERROR",
        errorMessage: error instanceof Error ? error.message : "Unknown error occurred",
      };
    } finally {
      setLoading(false);
    }
  };

  /**
   * Preview what platform initialization would do (dry run)
   */
  const previewInitialization = async (): Promise<Result<AdminInitializePlatformResponse>> => {
    return initializePlatform(true);
  };

  /**
   * Reverse sync assistants from UI database to LangGraph
   *
   * Recreates all assistants in LangGraph while preserving thread references
   * and permissions. Useful for local development when LangGraph state is lost.
   */
  const reverseSyncAssistants = async (): Promise<Result<ReverseSyncAssistantsResponse>> => {
    if (!isDevAdmin) {
      return {
        ok: false,
        errorCode: "PERMISSION_DENIED",
        errorMessage: "Only dev admins can reverse sync assistants",
      };
    }

    if (!session?.accessToken) {
      return {
        ok: false,
        errorCode: "NO_ACCESS_TOKEN",
        errorMessage: "No access token found",
      };
    }

    setLoading(true);
    try {
      const response = await fetch(`/api/langconnect/agents/admin/reverse-sync-assistants`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) {
        const errorText = await response.text();
        return {
          ok: false,
          errorCode: "REVERSE_SYNC_FAILED",
          errorMessage: `Failed to reverse sync assistants: ${response.status} ${errorText}`,
        };
      }

      const result: ReverseSyncAssistantsResponse = await response.json();

      // Invalidate all relevant caches and refresh UI immediately
      try {
        invalidateAssistantListCache();
        invalidateAllAssistantCaches();

        // Give the backend a brief moment to bump versions and finish sync, then refresh
        setTimeout(() => {
          refreshAgents(true);
        }, 200);
      } catch (_) {
        // No-op: cache invalidation is best-effort
      }

      return {
        ok: true,
        data: result,
      };

    } catch (error) {
      console.error("Error reverse syncing assistants:", error);

      return {
        ok: false,
        errorCode: "REVERSE_SYNC_ERROR",
        errorMessage: error instanceof Error ? error.message : "Unknown error occurred",
      };
    } finally {
      setLoading(false);
    }
  };

  return {
    loading,
    initializePlatform,
    previewInitialization,
    reverseSyncAssistants,
    isDevAdmin,
  };
} 