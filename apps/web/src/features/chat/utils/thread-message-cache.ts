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
  } catch (error) {
    console.error("[ThreadCache] Error reading cache index:", error);
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
        console.log(`[ThreadCache] Evicted old thread: ${evictedThreadId}`);
      }
    }

    index.lastUpdated = Date.now();
    localStorage.setItem(CACHE_INDEX_KEY, JSON.stringify(index));
  } catch (error) {
    console.error("[ThreadCache] Error updating cache index:", error);
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
      console.log(`[ThreadCache] Cache expired for thread ${threadId} (age: ${Math.round(age / 1000)}s)`);
      localStorage.removeItem(cacheKey);
      return null;
    }

    console.log(`[ThreadCache] ✅ Cache hit for thread ${threadId} (${parsedCache.messages.length} messages, age: ${Math.round(age / 1000)}s)`);
    return parsedCache;
  } catch (error) {
    console.error("[ThreadCache] Error reading thread cache:", error);
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
      console.warn(`[ThreadCache] ⚠️ Thread ${threadId} too large to cache (${sizeKB}KB > ${MAX_THREAD_CACHE_SIZE_KB}KB), skipping`);
      return;
    }

    console.log(`[ThreadCache] 💾 Caching thread ${threadId} (${messages.length} messages, ${sizeKB}KB)`);

    localStorage.setItem(cacheKey, serialized);

    // Update LRU index
    updateCacheIndex(threadId);
  } catch (error) {
    // Handle quota exceeded error
    if (error instanceof DOMException && error.name === 'QuotaExceededError') {
      console.warn("[ThreadCache] ⚠️ Quota exceeded, attempting cleanup...");

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

        console.log(`[ThreadCache] Cleared ${threadsToRemove.length} old thread caches, retrying...`);

        // Retry caching
        const cacheData: ThreadMessageCache = {
          threadId,
          assistantId,
          messages,
          timestamp: Date.now()
        };
        localStorage.setItem(`${CACHE_KEY_PREFIX}${threadId}`, JSON.stringify(cacheData));
        updateCacheIndex(threadId);
        console.log(`[ThreadCache] ✅ Successfully cached after cleanup`);
      } catch (_retryError) {
        // Retry failed - this is not critical, just means no caching for this thread
        console.warn(`[ThreadCache] Could not cache thread ${threadId} after cleanup - localStorage may be full. Thread will work normally without cache.`);
        // Don't throw - let the app continue without caching
      }
    } else {
      console.warn("[ThreadCache] Could not cache thread messages:", error);
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
    console.log(`[ThreadCache] Invalidated cache for thread ${threadId}`);

    // Remove from index
    const index = getCacheIndex();
    index.threadIds = index.threadIds.filter(id => id !== threadId);
    localStorage.setItem(CACHE_INDEX_KEY, JSON.stringify(index));
  } catch (error) {
    console.error("[ThreadCache] Error invalidating thread cache:", error);
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
    console.log(`[ThreadCache] Cleared all thread caches (${index.threadIds.length} threads)`);
  } catch (error) {
    console.error("[ThreadCache] Error clearing all thread caches:", error);
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
  } catch (error) {
    console.error("[ThreadCache] Error getting cache stats:", error);
    return { cachedThreads: 0, totalSizeKB: 0, oldestCacheAge: 0 };
  }
}
