import { useState, useCallback } from 'react';
import { Memory, MemoryResponse, MemoriesListResponse } from '@/types/memory';
import { toast } from 'sonner';
import { useAuthContext } from '@/providers/Auth';

export function useMemories() {
  const { session, isLoading: authLoading } = useAuthContext();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(false);
  const [initialSearchExecuted, setInitialSearchExecuted] = useState(false);

  // Normalize memory data from API response to consistent format
  const normalizeMemory = useCallback((rawMemory: any): Memory => {
    // Handle both normalized and raw API responses
    if (rawMemory.memory) {
      // Already normalized format
      return rawMemory;
    }

    // Raw format from mem0 - extract from payload
    const payload = rawMemory.payload || {};
    return {
      id: rawMemory.id,
      memory: payload.data || '',
      user_id: payload.user_id || '',
      hash: payload.hash || '',
      metadata: payload.metadata || {},
      created_at: payload.created_at || '',
      updated_at: payload.updated_at,
      payload: payload
    };
  }, []);

  // Fetch all memories for the current user
  const fetchMemories = useCallback(async (limit: number = 100, offset: number = 0): Promise<Memory[]> => {
    setLoading(true);
    
    if (authLoading || !session?.accessToken) {
      throw new Error('Authentication not ready or no token available');
    }
    
    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
      });

      const response = await fetch(`/api/langconnect/memory/all?${params}`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
        credentials: 'include',
      });

      if (!response.ok) {
        if (response.status === 503) {
          throw new Error('Memory service is not available. Please check server configuration.');
        }
        throw new Error(`Failed to fetch memories: ${response.statusText}`);
      }

      const result: MemoriesListResponse = await response.json();
      
      if (!result.success || !result.data?.results) {
        throw new Error(result.message || 'Failed to fetch memories');
      }

      // Normalize all memories
      const normalizedMemories = result.data.results.map(normalizeMemory);
      setMemories(normalizedMemories);
      setInitialSearchExecuted(true);
      
      return normalizedMemories;
    } catch (error) {
      console.error('Error fetching memories:', error);
      setInitialSearchExecuted(true); // Prevent infinite retry loop
      toast.error('Failed to load memories', {
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        richColors: true,
      });
      return [];
    } finally {
      setLoading(false);
    }
  }, [normalizeMemory, authLoading, session?.accessToken]);

  // Add a new memory
  const addMemory = useCallback(async (content: string, metadata?: Record<string, any>): Promise<Memory | null> => {
    if (!session?.accessToken) {
      throw new Error('No authentication token available');
    }
    
    try {
      const response = await fetch('/api/langconnect/memory/add', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.accessToken}`,
        },
        credentials: 'include',
        body: JSON.stringify({
          content,
          metadata,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to add memory: ${response.statusText}`);
      }

      const result: MemoryResponse = await response.json();
      
      if (!result.success) {
        throw new Error(result.message || 'Failed to add memory');
      }

      // Refresh memories to get the new one
      await fetchMemories();
      
      toast.success('Memory added successfully', {
        richColors: true,
      });

      return result.data;
    } catch (error) {
      console.error('Error adding memory:', error);
      toast.error('Failed to add memory', {
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        richColors: true,
      });
      return null;
    }
  }, [fetchMemories, session?.accessToken]);

  // Update an existing memory
  const updateMemory = useCallback(async (memoryId: string, content: string, metadata?: Record<string, any>): Promise<Memory | null> => {
    if (!session?.accessToken) {
      throw new Error('No authentication token available');
    }
    
    try {
      const response = await fetch(`/api/langconnect/memory/${memoryId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.accessToken}`,
        },
        credentials: 'include',
        body: JSON.stringify({
          content,
          metadata,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to update memory: ${response.statusText}`);
      }

      const result: MemoryResponse = await response.json();
      
      if (!result.success) {
        throw new Error(result.message || 'Failed to update memory');
      }

      // Update the local state
      setMemories(prev => prev.map(memory => 
        memory.id === memoryId 
          ? { ...memory, memory: content, metadata, updated_at: new Date().toISOString() }
          : memory
      ));
      
      toast.success('Memory updated successfully', {
        richColors: true,
      });

      return result.data;
    } catch (error) {
      console.error('Error updating memory:', error);
      toast.error('Failed to update memory', {
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        richColors: true,
      });
      return null;
    }
  }, [session?.accessToken]);

  // Delete a memory
  const deleteMemory = useCallback(async (memoryId: string, silent: boolean = false): Promise<boolean> => {
    if (!session?.accessToken) {
      throw new Error('No authentication token available');
    }

    try {
      const response = await fetch(`/api/langconnect/memory/${memoryId}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`Failed to delete memory: ${response.statusText}`);
      }

      const result: MemoryResponse = await response.json();

      if (!result.success) {
        throw new Error(result.message || 'Failed to delete memory');
      }

      // Remove from local state
      setMemories(prev => prev.filter(memory => memory.id !== memoryId));

      if (!silent) {
        toast.success('Memory deleted successfully', {
          richColors: true,
        });
      }

      return true;
    } catch (error) {
      console.error('Error deleting memory:', error);
      if (!silent) {
        toast.error('Failed to delete memory', {
          description: error instanceof Error ? error.message : 'Unknown error occurred',
          richColors: true,
        });
      }
      return false;
    }
  }, [session?.accessToken]);

  // Get a specific memory with full details
  const getMemory = useCallback(async (memoryId: string): Promise<Memory | null> => {
    if (!session?.accessToken) {
      throw new Error('No authentication token available');
    }
    
    try {
      const response = await fetch(`/api/langconnect/memory/${memoryId}`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`Failed to get memory: ${response.statusText}`);
      }

      const result: MemoryResponse = await response.json();
      
      if (!result.success) {
        throw new Error(result.message || 'Failed to get memory');
      }

      return normalizeMemory(result.data);
    } catch (error) {
      console.error('Error getting memory:', error);
      toast.error('Failed to load memory details', {
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        richColors: true,
      });
      return null;
    }
  }, [normalizeMemory, session?.accessToken]);

  // Delete all memories (with confirmation)
  const deleteAllMemories = useCallback(async (): Promise<boolean> => {
    if (!session?.accessToken) {
      throw new Error('No authentication token available');
    }
    
    try {
      const response = await fetch('/api/langconnect/memory/delete-all', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.accessToken}`,
        },
        credentials: 'include',
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        throw new Error(`Failed to delete all memories: ${response.statusText}`);
      }

      const result: MemoryResponse = await response.json();
      
      if (!result.success) {
        throw new Error(result.message || 'Failed to delete all memories');
      }

      // Clear local state
      setMemories([]);
      
      toast.success('All memories deleted successfully', {
        richColors: true,
      });

      return true;
    } catch (error) {
      console.error('Error deleting all memories:', error);
      toast.error('Failed to delete all memories', {
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        richColors: true,
      });
      return false;
    }
  }, [session?.accessToken]);

  return {
    memories,
    loading,
    initialSearchExecuted,
    fetchMemories,
    addMemory,
    updateMemory,
    deleteMemory,
    getMemory,
    deleteAllMemories,
  };
}
