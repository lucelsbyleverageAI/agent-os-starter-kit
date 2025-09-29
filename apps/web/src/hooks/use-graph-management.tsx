import { useState } from "react";
import { useAuthContext } from "@/providers/Auth";
import { useUserRole } from "@/providers/UserRole";
import { toast } from "sonner";

/**
 * Hook for graph management operations (dev admin only)
 */
export function useGraphManagement() {
  const { session } = useAuthContext();
  const { isDevAdmin } = useUserRole();
  const [loading, setLoading] = useState(false);

  /**
   * Initialize a new graph with default assistant and permissions
   */
  const initializeGraph = async (graphId: string, assistantName?: string) => {
    if (!isDevAdmin) {
      toast.error("Only dev admins can initialize graphs");
      return null;
    }

    if (!session?.accessToken) {
      toast.error("No access token found");
      return null;
    }

    setLoading(true);
    try {
      
      const response = await fetch(`/api/langconnect/graphs/${graphId}/initialize`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          assistant_name: assistantName || `Default ${graphId.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}`,
          grant_dev_admin_access: true,
          reason: "Graph initialization via frontend"
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to initialize graph: ${response.status} ${errorText}`);
      }

      const result = await response.json();
      
      toast.success(`Graph "${graphId}" initialized successfully!`, {
        description: `Created default assistant: ${result.assistant_name}`,
      });

            return result;

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      console.error('Failed to initialize graph:', errorMessage);
      
      toast.error("Failed to initialize graph", {
        description: errorMessage,
      });
      
      return null;
    } finally {
      setLoading(false);
    }
  };

  /**
   * Grant access to a graph for specified users
   */
  const grantGraphAccess = async (
    graphId: string, 
    users: Array<{ user_id: string; level: 'admin' | 'access' }>
  ) => {
    if (!isDevAdmin) {
      toast.error("Only dev admins can manage graph permissions");
      return null;
    }

    if (!session?.accessToken) {
      toast.error("No access token found");
      return null;
    }

    setLoading(true);
    try {
      
      const response = await fetch(`/api/langconnect/graphs/${graphId}/permissions`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          users,
          reason: "Graph access granted via frontend"
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to grant graph access: ${response.status} ${errorText}`);
      }

      const result = await response.json();
      
      toast.success(`Graph access granted!`, {
        description: `${result.successful_grants} users granted access to ${graphId}`,
      });

            return result;

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      console.error('Failed to grant graph access:', errorMessage);
      
      toast.error("Failed to grant graph access", {
        description: errorMessage,
      });
      
      return null;
    } finally {
      setLoading(false);
    }
  };

  /**
   * Get graph permissions (for viewing who has access)
   */
  const getGraphPermissions = async (graphId: string) => {
    if (!session?.accessToken) {
      toast.error("No access token found");
      return null;
    }

    try {
      const response = await fetch(`/api/langconnect/graphs/${graphId}/permissions`, {
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to get graph permissions: ${response.status} ${errorText}`);
      }

      const result = await response.json();
            return result;

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      console.error('Failed to get graph permissions:', errorMessage);
      
      toast.error("Failed to get graph permissions", {
        description: errorMessage,
      });
      
      return null;
    }
  };

  return {
    initializeGraph,
    grantGraphAccess,
    getGraphPermissions,
    loading,
    isDevAdmin,
  };
} 