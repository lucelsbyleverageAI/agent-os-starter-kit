import { useState } from "react";
import { useAuthContext } from "@/providers/Auth";
import { createClient } from "@/lib/client";

// Result types for consistent error handling
interface SuccessResult {
  ok: true;
}

interface ErrorResult {
  ok: false;
  errorCode: string;
  errorMessage: string;
}

type Result = SuccessResult | ErrorResult;

export function useThreadDeletion() {
  const { session } = useAuthContext();
  const [isDeleting, setIsDeleting] = useState(false);

  const deleteThread = async (threadId: string, deploymentId: string): Promise<Result> => {
    if (!session?.accessToken) {
      return {
        ok: false,
        errorCode: "NO_ACCESS_TOKEN",
        errorMessage: "Authentication required. Please sign in to delete threads.",
      };
    }

    setIsDeleting(true);
    try {
      // Prefer mirror-backed delete (handles LG delete + mirror cleanup atomically)
      const resp = await fetch(`/api/langconnect/agents/mirror/threads/${threadId}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });
      if (!resp.ok) {
        // Fallback to direct SDK delete if mirror route is unavailable
        const client = createClient(deploymentId, session.accessToken);
        await client.threads.delete(threadId);
      }
      
      return { ok: true };
    } catch (error) {
      console.error("Failed to delete thread:", error);
      return {
        ok: false,
        errorCode: "DELETE_FAILED",
        errorMessage: error instanceof Error ? error.message : "Failed to delete thread",
      };
    } finally {
      setIsDeleting(false);
    }
  };

  return {
    deleteThread,
    isDeleting,
  };
} 