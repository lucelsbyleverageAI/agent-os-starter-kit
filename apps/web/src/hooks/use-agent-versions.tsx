import { useState, useCallback } from "react";
import { useAuthContext } from "@/providers/Auth";
import {
  AssistantVersion,
  AssistantVersionsResponse,
  RestoreVersionRequest,
  RestoreVersionResponse,
} from "@/types/agent";
import { logger } from "@/lib/logger";
import { toast } from "sonner";

export function useAgentVersions(assistantId: string) {
  const { session } = useAuthContext();
  const [versions, setVersions] = useState<AssistantVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchVersions = useCallback(async () => {
    if (!session?.accessToken) {
      logger.warn("No access token available for fetchVersions");
      setError("No access token found");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/langconnect/agents/assistants/${assistantId}/versions`,
        {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        const errorText = await response.text();
        logger.error("Failed to fetch versions:", errorText);
        setError(`Failed to load version history: ${response.status}`);
        toast.error("Failed to load version history");
        return;
      }

      const data: AssistantVersionsResponse = await response.json();
      setVersions(data.versions);
      logger.log(`Fetched ${data.versions.length} versions for assistant ${assistantId}`);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Unknown error";
      logger.error("Error fetching versions:", err);
      setError(errorMessage);
      toast.error("Failed to load version history");
    } finally {
      setLoading(false);
    }
  }, [assistantId, session?.accessToken]);

  const restoreVersion = useCallback(
    async (
      versionNumber: number,
      commitMessage?: string
    ): Promise<boolean> => {
      if (!session?.accessToken) {
        logger.warn("No access token available for restoreVersion");
        toast.error("No access token found");
        return false;
      }

      try {
        const request: RestoreVersionRequest = {
          version: versionNumber,
          commit_message: commitMessage,
        };

        const response = await fetch(
          `/api/langconnect/agents/assistants/${assistantId}/restore`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${session.accessToken}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify(request),
          }
        );

        if (!response.ok) {
          const errorText = await response.text();
          logger.error("Failed to restore version:", errorText);
          toast.error(`Failed to restore version: ${response.status}`);
          return false;
        }

        const data: RestoreVersionResponse = await response.json();

        if (data.success) {
          toast.success(
            `Restored to version ${data.restored_from_version} (created v${data.new_version})`
          );
          logger.log(`Successfully restored assistant ${assistantId} to version ${versionNumber}`);

          // Refresh versions list to show the new version
          await fetchVersions();

          return true;
        } else {
          toast.error(data.message || "Failed to restore version");
          return false;
        }
      } catch (err) {
        logger.error("Error restoring version:", err);
        toast.error("Failed to restore version");
        return false;
      }
    },
    [assistantId, session?.accessToken, fetchVersions]
  );

  return {
    versions,
    loading,
    error,
    fetchVersions,
    restoreVersion,
  };
}
