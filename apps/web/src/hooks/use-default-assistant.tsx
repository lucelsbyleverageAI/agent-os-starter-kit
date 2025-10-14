import { useAuthContext } from "@/providers/Auth";
import { useCallback, useState, useEffect } from "react";

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

export interface DefaultAssistant {
  user_id: string;
  assistant_id: string;
  assistant_name?: string;
  graph_id?: string;
  created_at: string;
  updated_at: string;
}

export function useDefaultAssistant() {
  const { session } = useAuthContext();
  const [defaultAssistant, setDefaultAssistantState] = useState<DefaultAssistant | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getDefaultAssistant = useCallback(async (): Promise<Result<DefaultAssistant | null>> => {
    if (!session?.accessToken) {
      return {
        ok: false,
        errorCode: "NO_ACCESS_TOKEN",
        errorMessage: "No access token found",
      };
    }

    try {
      const response = await fetch("/api/langconnect/default-assistant", {
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        return {
          ok: false,
          errorCode: "FETCH_FAILED",
          errorMessage: `Failed to fetch default assistant: ${response.status}`,
        };
      }

      const data = await response.json();
      return {
        ok: true,
        data: data || null,
      };
    } catch (error) {
      return {
        ok: false,
        errorCode: "UNKNOWN_ERROR",
        errorMessage: error instanceof Error ? error.message : "Failed to fetch default assistant",
      };
    }
  }, [session?.accessToken]);

  const setDefaultAssistant = useCallback(
    async (assistantId: string): Promise<Result<DefaultAssistant>> => {
      if (!session?.accessToken) {
        return {
          ok: false,
          errorCode: "NO_ACCESS_TOKEN",
          errorMessage: "No access token found",
        };
      }

      try {
        const response = await fetch("/api/langconnect/default-assistant", {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ assistant_id: assistantId }),
        });

        if (!response.ok) {
          const errorText = await response.text();
          return {
            ok: false,
            errorCode: "SET_FAILED",
            errorMessage: `Failed to set default assistant: ${response.status} ${errorText}`,
          };
        }

        const data = await response.json();

        // Update internal state immediately
        setDefaultAssistantState(data);

        return {
          ok: true,
          data,
        };
      } catch (error) {
        return {
          ok: false,
          errorCode: "UNKNOWN_ERROR",
          errorMessage: error instanceof Error ? error.message : "Failed to set default assistant",
        };
      }
    },
    [session?.accessToken],
  );

  const clearDefaultAssistant = useCallback(async (): Promise<Result> => {
    if (!session?.accessToken) {
      console.warn("[useDefaultAssistant] No access token available for clearing default");
      return {
        ok: false,
        errorCode: "NO_ACCESS_TOKEN",
        errorMessage: "No access token found",
      };
    }

    try {
      console.log("[useDefaultAssistant] Clearing default assistant...");
      const response = await fetch("/api/langconnect/default-assistant", {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });

      console.log("[useDefaultAssistant] Clear response status:", response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error("[useDefaultAssistant] Failed to clear default assistant:", errorText);
        return {
          ok: false,
          errorCode: "CLEAR_FAILED",
          errorMessage: `Failed to clear default assistant: ${response.status} ${errorText}`,
        };
      }

      // Update internal state immediately
      setDefaultAssistantState(null);
      console.log("[useDefaultAssistant] Default assistant cleared successfully");

      return { ok: true };
    } catch (error) {
      console.error("[useDefaultAssistant] Error clearing default assistant:", error);
      return {
        ok: false,
        errorCode: "UNKNOWN_ERROR",
        errorMessage: error instanceof Error ? error.message : "Failed to clear default assistant",
      };
    }
  }, [session?.accessToken]);

  // Load default assistant on mount
  useEffect(() => {
    const loadDefault = async () => {
      setIsLoading(true);
      setError(null);
      const result = await getDefaultAssistant();
      if (result.ok) {
        setDefaultAssistantState(result.data || null);
      } else {
        setError(result.errorMessage);
      }
      setIsLoading(false);
    };

    if (session?.accessToken) {
      loadDefault();
    }
  }, [session?.accessToken, getDefaultAssistant]);

  // Refresh default assistant
  const refreshDefaultAssistant = useCallback(async () => {
    console.log("[useDefaultAssistant] Refreshing default assistant...");
    setIsLoading(true);
    setError(null);
    const result = await getDefaultAssistant();
    if (result.ok) {
      console.log("[useDefaultAssistant] Refresh successful, new default:", result.data);
      setDefaultAssistantState(result.data || null);
    } else {
      console.error("[useDefaultAssistant] Refresh failed:", result.errorMessage);
      setError(result.errorMessage);
    }
    setIsLoading(false);
  }, [getDefaultAssistant]);

  return {
    defaultAssistant,
    isLoading,
    error,
    getDefaultAssistant,
    setDefaultAssistant: setDefaultAssistant,
    clearDefaultAssistant,
    refreshDefaultAssistant,
  };
}
