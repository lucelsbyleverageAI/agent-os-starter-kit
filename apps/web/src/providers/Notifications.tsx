"use client";

import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import { useAuthContext } from "./Auth";
import { useAgentsContext } from './Agents';
import {
  NotificationInfo,
  NotificationContextType,

} from "@/types/notification";

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export const NotificationsProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const { session } = useAuthContext();
  const { 
    invalidateGraphDiscoveryCache, 
    invalidateAssistantListCache, 
    invalidateEnhancementStatusCache,
    invalidateAllAssistantCaches,
    refreshAgents,
    debugCacheState 
  } = useAgentsContext();
  const [notifications, setNotifications] = useState<NotificationInfo[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, _setIsLoading] = useState(false);
  const [isError, _setIsError] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchNotifications = useCallback(async () => {
    if (!session?.accessToken) {
      return;
    }

    try {
      const response = await fetch('/api/langconnect/notifications', {
        headers: {
          'Authorization': `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch notifications: ${response.status}`);
      }

      const data = await response.json();
      setNotifications(data.notifications || []);
      
             // Count unread notifications
       const unreadCount = (data.notifications || []).filter((n: any) => n.status === 'pending').length;
      setUnreadCount(unreadCount);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch notifications');
    }
  }, [session?.accessToken]);

  const acceptNotification = useCallback(async (notificationId: string, reason?: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/langconnect/notifications/${notificationId}/accept`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session?.accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          reason: reason || undefined
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to accept notification: ${response.status}`);
      }

      // Update local state and unread count
      setNotifications(prev => {
        const next = prev.map(n =>
          n.id === notificationId
            ? { ...n, status: 'accepted' as const, responded_at: new Date().toISOString() }
            : n
        );
        setUnreadCount(next.filter(n => n.status === 'pending').length);
        return next;
      });

      // Find the notification to get its details
      const notification = notifications.find(n => n.id === notificationId);
      if (notification) {
        // Invalidate caches impacted by permission changes
        try {
          invalidateGraphDiscoveryCache();
          invalidateAssistantListCache();
          invalidateEnhancementStatusCache();
          invalidateAllAssistantCaches?.();

          // Collections flow stays the same (dispatch event)
          if (notification.resource_type === 'collection' && typeof window !== 'undefined') {
            try {
              window.dispatchEvent(new CustomEvent('collections-cache-invalidated', {
                detail: { collectionId: notification.resource_id, type: 'permission_granted' }
              }));
            } catch (_error) {
              // Ignore event dispatch errors
            }
          }

          // Give backend a moment to write grants and bump cache versions, then refresh
          setTimeout(async () => {
            try {
              await refreshAgents?.(true);
            } catch (_error) {
              // Ignore event dispatch errors
            }
          }, 200);
        } catch (_e) {
          // Ignore cache invalidation errors
        }
      }

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept notification');
      return false;
    }
  }, [session?.accessToken, notifications, refreshAgents]);

  const rejectNotification = useCallback(async (notificationId: string, reason?: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/langconnect/notifications/${notificationId}/reject`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session?.accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          reason: reason || undefined
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to reject notification: ${response.status}`);
      }

      // Update local state and unread count
      setNotifications(prev => {
        const next = prev.map(n =>
          n.id === notificationId
            ? { ...n, status: 'rejected' as const, responded_at: new Date().toISOString() }
            : n
        );
        setUnreadCount(next.filter(n => n.status === 'pending').length);
        return next;
      });

      // No permission changes on reject, but we can still ensure discovery stays fresh if needed
      try {
        invalidateGraphDiscoveryCache();
        invalidateAssistantListCache();
        invalidateEnhancementStatusCache();
      } catch (_e) {
        // Ignore cache invalidation errors
      }

      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reject notification');
      return false;
    }
  }, [session?.accessToken, invalidateGraphDiscoveryCache, invalidateAssistantListCache, invalidateEnhancementStatusCache]);

  const markAsRead = useCallback((notificationId: string) => {
    // For optimistic UI updates - mark as read locally
    // This doesn't make API calls since the backend manages read state
    setNotifications(prev => 
      prev.map(n => 
        n.id === notificationId && n.status === 'pending'
          ? { ...n, status: 'pending' } // Keep status but indicate it's been seen
          : n
      )
    );
  }, []);

  // Load notifications when session changes
  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // Poll for new notifications every 30 seconds
  useEffect(() => {
    if (!session?.accessToken) return;

    const interval = setInterval(() => {
      fetchNotifications();
    }, 30000); // 30 seconds

    return () => clearInterval(interval);
  }, [session?.accessToken, fetchNotifications]);

  // Derived filtered notifications
  const pendingNotifications = useMemo(
    () => notifications.filter(n => n.status === 'pending'),
    [notifications]
  );

  const acceptedNotifications = useMemo(
    () => notifications.filter(n => n.status === 'accepted'),
    [notifications]
  );

  const rejectedNotifications = useMemo(
    () => notifications.filter(n => n.status === 'rejected'),
    [notifications]
  );

  const contextValue: NotificationContextType = {
    notifications,
    unreadCount,
    isLoading,
    isError,
    error,
    fetchNotifications,
    acceptNotification,
    rejectNotification,
    markAsRead,
    pendingNotifications,
    acceptedNotifications,
    rejectedNotifications,
    debugCacheState,
  };

  // Debug functions for development
  const debugClearAllCache = useCallback(() => {
    if (typeof window !== 'undefined') {
      // Clear agent-related caches
      const keys = Object.keys(localStorage).filter(key => 
        key.includes('agents_cache') || 
        key.includes('assistants_cache') ||
        key.includes('collections_cache')
      );
      keys.forEach(key => localStorage.removeItem(key));
      
      // Also dispatch cache invalidation events
      window.dispatchEvent(new CustomEvent('collections-cache-invalidated'));
    }
  }, []);

  const _debugRefreshAll = useCallback(async () => {
    try {
      debugClearAllCache();
      await fetchNotifications();
      await refreshAgents?.();
    } catch (_error) {
      // Manual refresh failed
    }
  }, [debugClearAllCache, fetchNotifications, refreshAgents]);

  // Debug: Add global functions for testing
  useEffect(() => { 
    if (typeof window !== 'undefined') {
      (window as any).debugNotifications = {
        debugCacheState,
        refreshAgents,
        invalidateAllCaches: () => {
          invalidateGraphDiscoveryCache();
          invalidateAssistantListCache();
          invalidateEnhancementStatusCache();

        },
        testRefresh: async () => {
          try {
            await refreshAgents();
          } catch (error) {
            console.error('❌ Manual refresh failed:', error);
          }
        }
      };
    }
  }, [debugCacheState, refreshAgents, invalidateGraphDiscoveryCache, invalidateAssistantListCache, invalidateEnhancementStatusCache]);

  return (
    <NotificationContext.Provider value={contextValue}>
      {children}
    </NotificationContext.Provider>
  );
};

/**
 * Hook to access notification context
 */
export const useNotifications = (): NotificationContextType => {
  const context = useContext(NotificationContext);
  if (context === undefined) {
    throw new Error("useNotifications must be used within a NotificationsProvider");
  }
  return context;
}; 