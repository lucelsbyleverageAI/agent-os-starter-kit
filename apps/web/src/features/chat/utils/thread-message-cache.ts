/**
 * Thread Message Cache Utilities
 *
 * Provides localStorage caching for thread messages to enable instant loading
 * of recently viewed conversations. Similar to agent caching in AgentsProvider.
 *
 * Cache Strategy:
 * - Store last 10 threads' messages (LRU eviction)
 * - 30 minute TTL per thread
 * - Quota-safe: ~5-10KB per thread (much smaller than agent configs)
 * - Automatic cleanup on quota exceeded
 */

import { Message } from "@langchain/langgraph-sdk";

const CACHE_KEY_PREFIX = "thread_messages_";
const CACHE_INDEX_KEY = "thread_cache_index";
const CACHE_TTL = 30 * 60 * 1000; // 30 minutes
const MAX_CACHED_THREADS = 10;
const MAX_THREAD_CACHE_SIZE_KB = 500; // Don't cache threads larger than 500KB

export interface ThreadMessageCache {
  threadId: string;
  assistantId: string | null;
  messages: Message[];
  timestamp: number;
}

interface CacheIndex {
  threadIds: string[]; // LRU ordered (most recent first)
  lastUpdated: number;
}

/**
 * Get cache index (tracks which threads are cached)
 */
function getCacheIndex(): CacheIndex {
  try {
    const cached = localStorage.getItem(CACHE_INDEX_KEY);
    if (!cached) {
      return { threadIds: [], lastUpdated: Date.now() };
    }
    return JSON.parse(cached);
  } catch (_error) {
    return { threadIds: [], lastUpdated: Date.now() };
  }
}

/**
 * Update cache index (LRU tracking)
 */
function updateCacheIndex(threadId: string): void {
  try {
    const index = getCacheIndex();

    // Remove thread if already in list
    index.threadIds = index.threadIds.filter(id => id !== threadId);

    // Add to front (most recent)
    index.threadIds.unshift(threadId);

    // Evict oldest if over limit
    if (index.threadIds.length > MAX_CACHED_THREADS) {
      const evictedThreadId = index.threadIds.pop();
      if (evictedThreadId) {
        // Remove evicted thread's cache
        localStorage.removeItem(`${CACHE_KEY_PREFIX}${evictedThreadId}`);
      }
    }

    index.lastUpdated = Date.now();
    localStorage.setItem(CACHE_INDEX_KEY, JSON.stringify(index));
  } catch (_error) {
    // Silently fail - caching is non-critical
  }
}

/**
 * Get cached thread messages
 */
export function getThreadMessageCache(threadId: string): ThreadMessageCache | null {
  if (!threadId) return null;

  try {
    const cacheKey = `${CACHE_KEY_PREFIX}${threadId}`;
    const cached = localStorage.getItem(cacheKey);

    if (!cached) {
      return null;
    }

    const parsedCache: ThreadMessageCache = JSON.parse(cached);

    // Check if cache is expired
    const age = Date.now() - parsedCache.timestamp;
    if (age > CACHE_TTL) {
      localStorage.removeItem(cacheKey);
      return null;
    }

    return parsedCache;
  } catch (_error) {
    return null;
  }
}

/**
 * Set cached thread messages
 */
export function setThreadMessageCache(
  threadId: string,
  assistantId: string | null,
  messages: Message[]
): void {
  if (!threadId || !messages || messages.length === 0) {
    return;
  }

  try {
    const cacheData: ThreadMessageCache = {
      threadId,
      assistantId,
      messages,
      timestamp: Date.now()
    };

    const cacheKey = `${CACHE_KEY_PREFIX}${threadId}`;
    const serialized = JSON.stringify(cacheData);
    const sizeKB = Math.round(serialized.length / 1024);

    // Check size before caching - skip if too large
    if (sizeKB > MAX_THREAD_CACHE_SIZE_KB) {
      return;
    }

    localStorage.setItem(cacheKey, serialized);

    // Update LRU index
    updateCacheIndex(threadId);
  } catch (error) {
    // Handle quota exceeded error
    if (error instanceof DOMException && error.name === 'QuotaExceededError') {
      try {
        // Clear oldest cached threads
        const index = getCacheIndex();
        const threadsToRemove = index.threadIds.slice(MAX_CACHED_THREADS / 2); // Remove half

        threadsToRemove.forEach(id => {
          localStorage.removeItem(`${CACHE_KEY_PREFIX}${id}`);
        });

        // Update index
        index.threadIds = index.threadIds.slice(0, MAX_CACHED_THREADS / 2);
        localStorage.setItem(CACHE_INDEX_KEY, JSON.stringify(index));

        // Retry caching
        const cacheData: ThreadMessageCache = {
          threadId,
          assistantId,
          messages,
          timestamp: Date.now()
        };
        localStorage.setItem(`${CACHE_KEY_PREFIX}${threadId}`, JSON.stringify(cacheData));
        updateCacheIndex(threadId);
      } catch (_retryError) {
        // Retry failed - this is not critical, just means no caching for this thread
        // Don't throw - let the app continue without caching
      }
    } else {
      // Don't throw - let the app continue without caching
    }
  }
}

/**
 * Invalidate cache for a specific thread
 */
export function invalidateThreadCache(threadId: string): void {
  if (!threadId) return;

  try {
    const cacheKey = `${CACHE_KEY_PREFIX}${threadId}`;
    localStorage.removeItem(cacheKey);

    // Remove from index
    const index = getCacheIndex();
    index.threadIds = index.threadIds.filter(id => id !== threadId);
    localStorage.setItem(CACHE_INDEX_KEY, JSON.stringify(index));
  } catch (_error) {
    // Silently fail - caching is non-critical
  }
}

/**
 * Clear all thread caches
 */
export function clearAllThreadCaches(): void {
  try {
    const index = getCacheIndex();

    index.threadIds.forEach(threadId => {
      localStorage.removeItem(`${CACHE_KEY_PREFIX}${threadId}`);
    });

    localStorage.removeItem(CACHE_INDEX_KEY);
  } catch (_error) {
    // Silently fail - caching is non-critical
  }
}

/**
 * Get cache statistics for monitoring
 */
export function getThreadCacheStats(): {
  cachedThreads: number;
  totalSizeKB: number;
  oldestCacheAge: number;
} {
  try {
    const index = getCacheIndex();
    let totalSize = 0;
    let oldestAge = 0;

    index.threadIds.forEach(threadId => {
      const cached = localStorage.getItem(`${CACHE_KEY_PREFIX}${threadId}`);
      if (cached) {
        totalSize += cached.length;
        const parsedCache = JSON.parse(cached) as ThreadMessageCache;
        const age = Date.now() - parsedCache.timestamp;
        if (age > oldestAge) {
          oldestAge = age;
        }
      }
    });

    return {
      cachedThreads: index.threadIds.length,
      totalSizeKB: Math.round(totalSize / 1024),
      oldestCacheAge: Math.round(oldestAge / 1000) // seconds
    };
  } catch (_error) {
    return { cachedThreads: 0, totalSizeKB: 0, oldestCacheAge: 0 };
  }
}
