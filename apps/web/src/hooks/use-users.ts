import { useState, useCallback, useRef, useEffect } from 'react';
import { useAuthContext } from '@/providers/Auth';
import { 
  CollaborativeUser, 
  UserSearchOptions, 
  UsersResponse,
  UserSearchResponse 
} from '@/types/user';
import { toast } from 'sonner';

interface UseUsersReturn {
  users: CollaborativeUser[];
  loading: boolean;
  error: string | null;
  searchResults: CollaborativeUser[];
  searchLoading: boolean;
  fetchUsers: () => Promise<void>;
  searchUsers: (query: string, options?: UserSearchOptions) => Promise<CollaborativeUser[]>;
  clearSearch: () => void;
  refreshUsers: () => Promise<void>;
  getUserById: (id: string) => CollaborativeUser | undefined;
  getUsersByIds: (ids: string[]) => Promise<CollaborativeUser[]>;
  getUsersByIdsSync: (ids: string[]) => CollaborativeUser[];
}

// Cache configuration
const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
const SEARCH_DEBOUNCE_MS = 300;

function getApiUrlOrThrow(): URL {
  if (typeof window === 'undefined') {
    // Server-side: use localhost
    return new URL('http://localhost:3000');
  }
  // Client-side: use current origin
  return new URL(window.location.origin);
}

export function useUsers(): UseUsersReturn {
  const { session } = useAuthContext();
  const [users, setUsers] = useState<CollaborativeUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<CollaborativeUser[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  
  // Cache management
  const cacheRef = useRef<{
    users: CollaborativeUser[];
    lastFetch: number;
  }>({ users: [], lastFetch: 0 });
  
  // Search debouncing
  const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Check if cache is valid
  const isCacheValid = useCallback(() => {
    const now = Date.now();
    return (now - cacheRef.current.lastFetch) < CACHE_DURATION;
  }, []);

  // Fetch users from our secure API endpoint
  const fetchUsersFromAPI = useCallback(async (): Promise<CollaborativeUser[]> => {
    if (!session?.accessToken) {
      throw new Error('No authentication token available');
    }

    const url = getApiUrlOrThrow();
    url.pathname = '/api/users';

    const response = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${session.accessToken}`,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `Failed to fetch users: ${response.statusText}`);
    }

    const data: UsersResponse = await response.json();
    return data.users;
  }, [session?.accessToken]);

  // Main fetch users function with caching
  const fetchUsers = useCallback(async () => {
    // Return cached data if valid
    if (isCacheValid() && cacheRef.current.users.length > 0) {
      setUsers(cacheRef.current.users);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const fetchedUsers = await fetchUsersFromAPI();
      
      // Update cache
      cacheRef.current = {
        users: fetchedUsers,
        lastFetch: Date.now(),
      };
      
      setUsers(fetchedUsers);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch users';
      setError(errorMessage);
      console.error('Error fetching users:', err);
      
      // Show user-friendly error
      toast.error('Unable to load team members', {
        description: 'Please check your permissions and try again.',
        richColors: true,
      });
    } finally {
      setLoading(false);
    }
  }, [isCacheValid, fetchUsersFromAPI]);

  // Search users with debouncing
  const searchUsers = useCallback(async (
    query: string, 
    options: UserSearchOptions = {}
  ): Promise<CollaborativeUser[]> => {
    // Clear existing timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    return new Promise((resolve) => {
      searchTimeoutRef.current = setTimeout(async () => {
        if (!query.trim()) {
          setSearchResults([]);
          resolve([]);
          return;
        }

        setSearchLoading(true);

        try {
          // First try client-side search from cache if available
          if (isCacheValid() && cacheRef.current.users.length > 0) {
            const filtered = cacheRef.current.users.filter(user => {
              const searchTerm = query.toLowerCase();
              const matchesEmail = user.email.toLowerCase().includes(searchTerm);
              const matchesDisplayName = user.display_name?.toLowerCase().includes(searchTerm);
              const matchesFirstName = user.first_name?.toLowerCase().includes(searchTerm);
              const matchesLastName = user.last_name?.toLowerCase().includes(searchTerm);
              const isExcluded = options.exclude_user_ids?.includes(user.id);
              
              return (matchesEmail || matchesDisplayName || matchesFirstName || matchesLastName) && !isExcluded;
            });

            setSearchResults(filtered);
            resolve(filtered);
          } else {
            // Fallback to server search
            if (!session?.accessToken) {
              throw new Error('No authentication token available');
            }

            const url = getApiUrlOrThrow();
            url.pathname = '/api/users';
            url.searchParams.set('q', query);
            
            if (options.exclude_user_ids?.length) {
              url.searchParams.set('exclude', options.exclude_user_ids.join(','));
            }
            if (options.limit) {
              url.searchParams.set('limit', options.limit.toString());
            }

            const response = await fetch(url.toString(), {
              headers: {
                Authorization: `Bearer ${session.accessToken}`,
              },
            });

            if (!response.ok) {
              throw new Error(`Search failed: ${response.statusText}`);
            }

            const data: UserSearchResponse = await response.json();
            setSearchResults(data.users);
            resolve(data.users);
          }
        } catch (_err) {
          setSearchResults([]);
          resolve([]);
        } finally {
          setSearchLoading(false);
        }
      }, SEARCH_DEBOUNCE_MS);
    });
  }, [session?.accessToken, isCacheValid]);

  // Clear search results
  const clearSearch = useCallback(() => {
    setSearchResults([]);
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
  }, []);

  // Force refresh users (bypass cache)
  const refreshUsers = useCallback(async () => {
    cacheRef.current = { users: [], lastFetch: 0 };
    await fetchUsers();
  }, [fetchUsers]);

  // Get user by ID from cache
  const getUserById = useCallback((id: string): CollaborativeUser | undefined => {
    return cacheRef.current.users.find(user => user.id === id) || 
           users.find(user => user.id === id);
  }, [users]);

  // Get multiple users by IDs
  const getUsersByIds = useCallback(async (ids: string[]): Promise<CollaborativeUser[]> => {
    if (ids.length === 0) return [];
    
    const allUsers = cacheRef.current.users.length > 0 ? cacheRef.current.users : users;
    const foundUsers = ids.map(id => allUsers.find(user => user.id === id)).filter(Boolean) as CollaborativeUser[];
    const missingIds = ids.filter(id => !allUsers.find(user => user.id === id));
    
    // If we have all users, return them immediately
    if (missingIds.length === 0) {
      return foundUsers;
    }
    
    // If we have missing users and authentication, try to fetch them
    if (session?.accessToken && missingIds.length > 0) {
      try {
        const url = getApiUrlOrThrow();
        url.pathname = '/api/users';
        url.searchParams.set('ids', missingIds.join(','));

        const response = await fetch(url.toString(), {
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
        });

        if (response.ok) {
          const data: UsersResponse = await response.json();
          const fetchedUsers = data.users;
          
          // Update cache with new users
          const updatedUsers = [...allUsers, ...fetchedUsers];
          cacheRef.current = {
            users: updatedUsers,
            lastFetch: Date.now(),
          };
          
          // Update state
          setUsers(updatedUsers);
          
          // Return all requested users
          return ids.map(id => updatedUsers.find(user => user.id === id)).filter(Boolean) as CollaborativeUser[];
        }
      } catch (_error) {
        // Error fetching missing users - continue with what we have
      }
    }
    
    // Return what we have, even if some are missing
    return foundUsers;
  }, [users, session?.accessToken]);

  // Synchronous version for immediate access to cached data
  const getUsersByIdsSync = useCallback((ids: string[]): CollaborativeUser[] => {
    const allUsers = cacheRef.current.users.length > 0 ? cacheRef.current.users : users;
    return ids.map(id => allUsers.find(user => user.id === id)).filter(Boolean) as CollaborativeUser[];
  }, [users]);

  // Auto-fetch on mount if authenticated
  useEffect(() => {
    if (session?.accessToken && !loading && users.length === 0) {
      fetchUsers();
    }
  }, [session?.accessToken, fetchUsers, loading, users.length]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, []);

  return {
    users,
    loading,
    error,
    searchResults,
    searchLoading,
    fetchUsers,
    searchUsers,
    clearSearch,
    refreshUsers,
    getUserById,
    getUsersByIds,
    getUsersByIdsSync,
  };
} 