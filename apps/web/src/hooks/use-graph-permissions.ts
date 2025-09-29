import { useState, useCallback, useRef } from 'react';
import { useAuthContext } from '@/providers/Auth';
import { toast } from 'sonner';

interface GraphPermission {
  id: string;
  graph_id: string;
  user_id: string;
  permission_level: 'admin' | 'access';
  granted_by: string;
  created_at: string;
  updated_at: string;
}

interface GraphPermissionsResponse {
  permissions: GraphPermission[];
  total_count: number;
  user_permission_level?: 'admin' | 'access' | null;
}

interface UseGraphPermissionsReturn {
  permissions: GraphPermission[];
  userPermissionLevel: 'admin' | 'access' | null;
  loading: boolean;
  error: string | null;
  fetchPermissions: (graphId: string) => Promise<void>;
  refreshPermissions: (graphId: string) => Promise<void>;
  getUserPermissionLevel: (graphId: string) => 'admin' | 'access' | null;
  grantPermissions: (graphId: string, permissions: Array<{user_id: string, permission_level: 'admin' | 'access'}>) => Promise<{success: boolean, errors?: string[]}>;
  revokePermission: (graphId: string, userId: string) => Promise<void>;
  revokeMyGraphAccess: (graphId: string) => Promise<boolean>;
}

// Cache configuration
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

interface PermissionCache {
  [graphId: string]: {
    data: GraphPermissionsResponse;
    lastFetch: number;
  };
}

function getApiUrlOrThrow(): URL {
  if (typeof window === 'undefined') {
    // Server-side: use localhost
    return new URL('http://localhost:3000');
  }
  // Client-side: use current origin
  return new URL(window.location.origin);
}

export function useGraphPermissions(): UseGraphPermissionsReturn {
  const { session, user } = useAuthContext();
  const [permissions, setPermissions] = useState<GraphPermission[]>([]);
  const [userPermissionLevel, setUserPermissionLevel] = useState<'admin' | 'access' | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Cache management
  const cacheRef = useRef<PermissionCache>({});

  // Check if cache is valid for a specific graph
  const isCacheValid = useCallback((graphId: string) => {
    const cached = cacheRef.current[graphId];
    if (!cached) return false;
    
    const now = Date.now();
    return (now - cached.lastFetch) < CACHE_DURATION;
  }, []);

  // Fetch permissions for a specific graph
  const fetchPermissionsFromAPI = useCallback(async (graphId: string): Promise<GraphPermissionsResponse> => {
    if (!session?.accessToken) {
      throw new Error('No authentication token available');
    }

    const url = getApiUrlOrThrow();
    url.pathname = `/api/langconnect/agents/graphs/${graphId}/permissions`;

    const response = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `Failed to fetch permissions: ${response.statusText}`);
    }

    const data: GraphPermissionsResponse = await response.json();
    
    // Fallback: Calculate user permission level if not provided by API
    if (!data.user_permission_level && user?.id && data.permissions) {
      const userPermission = data.permissions.find(p => p.user_id === user.id);
      if (userPermission) {
        data.user_permission_level = userPermission.permission_level;
      }
    }
    
    return data;
  }, [session?.accessToken, user?.id]);

  // Main fetch permissions function with caching
  const fetchPermissions = useCallback(async (graphId: string) => {
    // Return cached data if valid
    if (isCacheValid(graphId)) {
      const cached = cacheRef.current[graphId];
      setPermissions(cached.data.permissions);
      setUserPermissionLevel(cached.data.user_permission_level || null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await fetchPermissionsFromAPI(graphId);
      
      // Update cache
      cacheRef.current[graphId] = {
        data,
        lastFetch: Date.now(),
      };
      
      setPermissions(data.permissions);
      setUserPermissionLevel(data.user_permission_level || null);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch permissions';
      setError(errorMessage);
      
      // Don't show toast for permission errors (user might not have access)
      const isPermissionError = errorMessage.includes('Forbidden') || 
                                errorMessage.includes('403') ||
                                errorMessage.includes('Only graph admins can view') ||
                                errorMessage.includes('admin') ||
                                errorMessage.toLowerCase().includes('permission');
      
      if (!isPermissionError) {
        toast.error('Unable to load graph permissions', {
          description: 'Please check your permissions and try again.',
          richColors: true,
        });
      }
    } finally {
      setLoading(false);
    }
  }, [isCacheValid, fetchPermissionsFromAPI]);

  // Force refresh permissions (bypass cache)
  const refreshPermissions = useCallback(async (graphId: string) => {
    delete cacheRef.current[graphId];
    await fetchPermissions(graphId);
  }, [fetchPermissions]);

  // Get user permission level for a specific graph from cache
  const getUserPermissionLevel = useCallback((graphId: string): 'admin' | 'access' | null => {
    const cached = cacheRef.current[graphId];
    const level = cached?.data.user_permission_level || null;
    return level;
  }, []);

  // Grant permissions to a specific graph
  const grantPermissions = useCallback(async (graphId: string, permissions: Array<{user_id: string, permission_level: 'admin' | 'access'}>): Promise<{success: boolean, errors?: string[]}> => {
    setLoading(true);
    setError(null);

    try {
      if (!session?.accessToken) {
        throw new Error('No authentication token available');
      }

      const url = getApiUrlOrThrow();
      url.pathname = `/api/langconnect/agents/graphs/${graphId}/permissions`;

      // Convert permissions format to match backend API
      const requestBody = {
        users: permissions.map(p => ({
          user_id: p.user_id,
          level: p.permission_level  // Backend expects 'level' not 'permission_level'
        }))
      };

      const response = await fetch(url.toString(), {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        return { success: false, errors: [errorData.error || `Failed to grant permissions: ${response.statusText}`] };
      }

      const grantResponse = await response.json();
      
      // Check if the grant was successful
      const wasSuccessful = grantResponse.successful_grants > 0;
      const errors = grantResponse.errors || [];
      
      if (wasSuccessful) {
        // Refresh permissions to get updated list
        delete cacheRef.current[graphId]; // Clear cache to force fresh fetch
        await fetchPermissions(graphId);
      }
      
      return { 
        success: wasSuccessful && errors.length === 0, 
        errors: errors.length > 0 ? errors : undefined 
      };
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to grant permissions';
      setError(errorMessage);
      
      // Don't show toast for permission errors (user might not have access)
      const isPermissionError = errorMessage.includes('Forbidden') || 
                                errorMessage.includes('403') ||
                                errorMessage.includes('Only graph admins can') ||
                                errorMessage.includes('admin') ||
                                errorMessage.toLowerCase().includes('permission');
      
      if (!isPermissionError) {
        toast.error('Unable to grant graph permissions', {
          description: 'Please check your permissions and try again.',
          richColors: true,
        });
      }
      return { success: false, errors: [errorMessage] };
    } finally {
      setLoading(false);
    }
  }, [session?.accessToken]);

  // Revoke permission from a specific graph
  const revokePermission = useCallback(async (graphId: string, userId: string): Promise<void> => {
    setLoading(true);
    setError(null);

    try {
      if (!session?.accessToken) {
        throw new Error('No authentication token available');
      }

      const url = getApiUrlOrThrow();
      url.pathname = `/api/langconnect/agents/graphs/${graphId}/permissions/${userId}`;

      const response = await fetch(url.toString(), {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Failed to revoke permission: ${response.statusText}`);
      }

      // Clear cache and refresh permissions to get updated list
      delete cacheRef.current[graphId];
      await fetchPermissions(graphId);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to revoke permission';
      setError(errorMessage);
      
      // Don't show toast for permission errors (user might not have access)
      const isPermissionError = errorMessage.includes('Forbidden') || 
                                errorMessage.includes('403') ||
                                errorMessage.includes('Only graph admins can') ||
                                errorMessage.includes('admin') ||
                                errorMessage.toLowerCase().includes('permission');
      
      if (!isPermissionError) {
        toast.error('Unable to revoke graph permission', {
          description: 'Please check your permissions and try again.',
          richColors: true,
        });
      }
    } finally {
      setLoading(false);
    }
  }, [session?.accessToken, fetchPermissions]);

  // Revoke my graph access (self-revocation)
  const revokeMyGraphAccess = useCallback(async (graphId: string): Promise<boolean> => {
    
    if (!user?.id) {
      toast.error('User ID not found');
      return false;
    }

    if (!session?.accessToken) {
      toast.error('No authentication token available');
      return false;
    }

    setLoading(true);
    setError(null);

    try {
      const url = getApiUrlOrThrow();
      url.pathname = `/api/langconnect/agents/graphs/${graphId}/permissions/${user.id}`;

      const response = await fetch(url.toString(), {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        
        if (response.status === 403) {
          toast.error('Cannot revoke access', {
            description: errorData.detail || 'You may be a dev admin or lack permission to revoke access.',
          });
        } else {
          toast.error('Failed to revoke access', {
            description: errorData.detail || 'Please try again.',
          });
        }
        return false;
      }

      toast.success('Access revoked successfully', {
        description: `You no longer have access to ${graphId}`,
      });
      
      return true;
    } catch (err) {
      const _errorMessage = err instanceof Error ? err.message : 'Failed to revoke graph access';
      
      toast.error('Failed to revoke access', {
        description: 'Please try again.',
      });
      
      return false;
    } finally {
      setLoading(false);
    }
  }, [session?.accessToken, user?.id]);

  return {
    permissions,
    userPermissionLevel,
    loading,
    error,
    fetchPermissions,
    refreshPermissions,
    getUserPermissionLevel,
    grantPermissions,
    revokePermission,
    revokeMyGraphAccess,
  };
} 