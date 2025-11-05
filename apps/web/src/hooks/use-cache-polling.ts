/**
 * Cache Polling Hook
 *
 * Polls the /cache-state endpoint every 30 seconds to detect backend data changes.
 * Returns version numbers that components can watch to trigger refetching.
 *
 * This enables multi-tab synchronization:
 * - Tab A creates/updates data → backend increments version
 * - Tab B polls → sees new version → refetches data
 *
 * Pattern matches Agents Provider (apps/web/src/providers/Agents.tsx:677-715)
 */

import { useState, useEffect, useCallback } from 'react';
import { useAuthContext } from '@/providers/Auth';

interface CacheState {
  graphs_version: number;
  assistants_version: number;
  schemas_version: number;
  threads_version: number;
}

interface UseCachePollingReturn {
  graphsVersion: number | null;
  assistantsVersion: number | null;
  schemasVersion: number | null;
  threadsVersion: number | null;
  isPolling: boolean;
}

/**
 * Hook to poll cache state and track version numbers.
 *
 * @param enabled - Whether polling is enabled (default: true)
 * @param interval - Polling interval in milliseconds (default: 30000)
 * @returns Object containing version numbers and polling status
 *
 * @example
 * ```tsx
 * const { threadsVersion } = useCachePolling();
 *
 * useEffect(() => {
 *   if (threadsVersion !== null) {
 *     refreshThreads();
 *   }
 * }, [threadsVersion]);
 * ```
 */
export function useCachePolling(
  enabled: boolean = true,
  interval: number = 30000
): UseCachePollingReturn {
  const { session } = useAuthContext();

  const [graphsVersion, setGraphsVersion] = useState<number | null>(null);
  const [assistantsVersion, setAssistantsVersion] = useState<number | null>(null);
  const [schemasVersion, setSchemasVersion] = useState<number | null>(null);
  const [threadsVersion, setThreadsVersion] = useState<number | null>(null);
  const [isPolling, setIsPolling] = useState<boolean>(false);

  /**
   * Fetch current cache state from backend.
   *
   * Polling frequency: Every 30 seconds (default)
   * Why 30s? Balance between responsiveness and server load:
   * - Shorter (e.g., 10s) = Too many requests for marginal benefit
   * - Longer (e.g., 60s) = Users wait longer to see changes from other tabs
   *
   * With WebSockets/SSE, this polling would be eliminated entirely.
   */
  const fetchCacheState = useCallback(async () => {
    if (!session?.accessToken) return;

    try {
      setIsPolling(true);

      const res = await fetch(`/api/langconnect/agents/mirror/cache-state`, {
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (!res.ok) return;

      const data: CacheState = await res.json();

      setGraphsVersion(data.graphs_version ?? null);
      setAssistantsVersion(data.assistants_version ?? null);
      setSchemasVersion(data.schemas_version ?? null);
      setThreadsVersion(data.threads_version ?? null);
    } catch (_e) {
      // Silently fail - prevents errors during network issues or API downtime
      // Components will continue using stale data until polling recovers
    } finally {
      setIsPolling(false);
    }
  }, [session?.accessToken]);

  /**
   * Poll cache state every N seconds for version-aware invalidation.
   *
   * This is the heartbeat of multi-tab synchronization. Without this polling,
   * tabs would only see changes on page refresh.
   *
   * The interval is cleaned up when component unmounts or user logs out.
   */
  useEffect(() => {
    if (!enabled || !session?.accessToken) return;

    // Fetch immediately on mount
    fetchCacheState();

    // Then poll at specified interval
    const pollInterval = setInterval(fetchCacheState, interval);

    return () => clearInterval(pollInterval);
  }, [enabled, session?.accessToken, interval, fetchCacheState]);

  return {
    graphsVersion,
    assistantsVersion,
    schemasVersion,
    threadsVersion,
    isPolling,
  };
}
