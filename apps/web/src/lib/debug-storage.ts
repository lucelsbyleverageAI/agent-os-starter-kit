/**
 * LocalStorage Debugging Utilities
 *
 * Run these functions in the browser console to analyze and clean up localStorage
 *
 * Usage:
 *   import { analyzeStorage, clearOldData } from '@/lib/debug-storage'
 *   analyzeStorage() // See what's stored
 *   clearOldData()   // Clean up old caches
 */

export interface StorageItem {
  key: string;
  sizeKB: number;
  sizeBytes: number;
  preview: string;
  type: string;
}

export interface StorageAnalysis {
  totalSizeKB: number;
  totalSizeMB: number;
  itemCount: number;
  items: StorageItem[];
  byCategory: {
    category: string;
    count: number;
    sizeKB: number;
    keys: string[];
  }[];
  quota?: {
    usedMB: number;
    totalMB: number;
    percentUsed: number;
  };
}

/**
 * Analyze localStorage usage
 */
export function analyzeStorage(): StorageAnalysis {
  const items: StorageItem[] = [];
  let totalBytes = 0;

  // Analyze each item
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key) continue;

    const value = localStorage.getItem(key) || '';
    const sizeBytes = new Blob([value]).size;
    totalBytes += sizeBytes;

    // Parse to detect data type
    let type = 'string';
    let parsed: any = value;
    try {
      parsed = JSON.parse(value);
      if (Array.isArray(parsed)) type = 'array';
      else if (typeof parsed === 'object') type = 'object';
    } catch {
      // Not JSON
    }

    items.push({
      key,
      sizeKB: Math.round(sizeBytes / 1024),
      sizeBytes,
      preview: value.substring(0, 100),
      type,
    });
  }

  // Sort by size (largest first)
  items.sort((a, b) => b.sizeBytes - a.sizeBytes);

  // Categorize by key prefix
  const categories = new Map<string, { count: number; sizeKB: number; keys: string[] }>();

  items.forEach((item) => {
    // Detect category from key pattern
    let category = 'other';

    if (item.key.startsWith('thread_messages_')) category = 'thread_cache';
    else if (item.key.startsWith('thread_cache_')) category = 'thread_cache_index';
    else if (item.key.startsWith('agent_')) category = 'agent_cache';
    else if (item.key.includes('assistant')) category = 'assistant_data';
    else if (item.key.includes('graph')) category = 'graph_data';
    else if (item.key.includes('auth') || item.key.includes('token')) category = 'auth';
    else if (item.key.startsWith('sb-')) category = 'supabase';
    else if (item.key.includes('config')) category = 'config';
    else if (item.key.includes('ui') || item.key.includes('theme')) category = 'ui_state';

    const cat = categories.get(category) || { count: 0, sizeKB: 0, keys: [] };
    cat.count++;
    cat.sizeKB += item.sizeKB;
    cat.keys.push(item.key);
    categories.set(category, cat);
  });

  // Sort categories by size
  const byCategory = Array.from(categories.entries())
    .map(([category, data]) => ({ category, ...data }))
    .sort((a, b) => b.sizeKB - a.sizeKB);

  // Try to get storage quota (only works in some browsers)
  let quota: StorageAnalysis['quota'];
  if ('storage' in navigator && 'estimate' in navigator.storage) {
    // We'll fetch this async, so return a placeholder
    navigator.storage.estimate().then((estimate) => {
      const used = estimate.usage || 0;
      const total = estimate.quota || 0;
      console.log('📊 Storage Quota:', {
        usedMB: (used / 1024 / 1024).toFixed(2),
        totalMB: (total / 1024 / 1024).toFixed(2),
        percentUsed: ((used / total) * 100).toFixed(1) + '%',
      });
    });
  }

  const totalSizeKB = Math.round(totalBytes / 1024);
  const analysis: StorageAnalysis = {
    totalSizeKB,
    totalSizeMB: Math.round((totalSizeKB / 1024) * 100) / 100,
    itemCount: items.length,
    items,
    byCategory,
    quota,
  };

  // Print nice console output
  // eslint-disable-next-line no-console
  console.group('📦 LocalStorage Analysis');
  console.log(`Total Size: ${analysis.totalSizeMB} MB (${totalSizeKB} KB)`);
  console.log(`Total Items: ${analysis.itemCount}`);
  console.log('');

  console.log('📊 By Category:');
  // eslint-disable-next-line no-console
  console.table(byCategory.map(c => ({
    Category: c.category,
    Items: c.count,
    'Size (KB)': c.sizeKB,
    'Size (MB)': (c.sizeKB / 1024).toFixed(2),
  })));

  console.log('');
  console.log('🔝 Top 10 Largest Items:');
  // eslint-disable-next-line no-console
  console.table(items.slice(0, 10).map(item => ({
    Key: item.key.length > 50 ? item.key.substring(0, 47) + '...' : item.key,
    'Size (KB)': item.sizeKB,
    Type: item.type,
    Preview: item.preview.substring(0, 50) + (item.preview.length > 50 ? '...' : ''),
  })));

  console.log('');
  console.log('💡 To clear specific categories:');
  console.log('  clearThreadCache()        - Clear all thread message caches');
  console.log('  clearAgentCache()         - Clear agent configuration caches');
  console.log('  clearOldData()            - Clear everything except auth/config');
  console.log('  clearByPattern("prefix")  - Clear keys matching pattern');

  // eslint-disable-next-line no-console
  console.groupEnd();

  return analysis;
}

/**
 * Clear thread message caches
 */
export function clearThreadCache(): void {
  let cleared = 0;
  const keys: string[] = [];

  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (key && (key.startsWith('thread_messages_') || key.startsWith('thread_cache_'))) {
      keys.push(key);
      localStorage.removeItem(key);
      cleared++;
    }
  }

  console.log(`✅ Cleared ${cleared} thread cache items`);
  console.log('Keys removed:', keys);
}

/**
 * Clear agent configuration caches
 */
export function clearAgentCache(): void {
  let cleared = 0;
  const keys: string[] = [];

  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (key && (key.startsWith('agent_') || key.includes('assistant_cache') || key.includes('graph_cache'))) {
      keys.push(key);
      localStorage.removeItem(key);
      cleared++;
    }
  }

  console.log(`✅ Cleared ${cleared} agent cache items`);
  console.log('Keys removed:', keys);
}

/**
 * Clear all cache data (keep auth and critical config)
 */
export function clearOldData(): void {
  const keysToKeep = new Set<string>();
  const keysToRemove = new Set<string>();

  // Identify keys to keep
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key) continue;

    // Keep auth tokens, supabase session, critical config
    if (
      key.includes('auth') ||
      key.includes('token') ||
      key.startsWith('sb-') ||
      key === 'theme' ||
      key === 'locale' ||
      key.includes('user_preferences')
    ) {
      keysToKeep.add(key);
    } else {
      keysToRemove.add(key);
    }
  }

  // Remove cache data
  keysToRemove.forEach((key) => {
    localStorage.removeItem(key);
  });

  console.log(`✅ Cleared ${keysToRemove.size} cache items`);
  console.log(`🔒 Kept ${keysToKeep.size} important items:`, Array.from(keysToKeep));
  console.log('Removed:', Array.from(keysToRemove));
}

/**
 * Clear keys matching a pattern
 */
export function clearByPattern(pattern: string): void {
  const keysToRemove: string[] = [];

  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (key && key.includes(pattern)) {
      keysToRemove.push(key);
      localStorage.removeItem(key);
    }
  }

  console.log(`✅ Cleared ${keysToRemove.length} items matching "${pattern}"`);
  console.log('Removed:', keysToRemove);
}

/**
 * Get detailed info about a specific key
 */
export function inspectKey(key: string): void {
  const value = localStorage.getItem(key);

  if (!value) {
    console.log(`❌ Key "${key}" not found`);
    return;
  }

  const sizeBytes = new Blob([value]).size;
  const sizeKB = Math.round(sizeBytes / 1024);

  console.group(`🔍 Inspecting: ${key}`);
  console.log(`Size: ${sizeKB} KB (${sizeBytes} bytes)`);

  try {
    const parsed = JSON.parse(value);
    console.log('Type: JSON');
    console.log('Parsed value:', parsed);

    // Special handling for known cache types
    if (key.startsWith('thread_messages_')) {
      console.log('Thread ID:', parsed.threadId);
      console.log('Messages:', parsed.messages?.length || 0);
      console.log('Cached at:', new Date(parsed.timestamp));
      console.log('Age (minutes):', Math.round((Date.now() - parsed.timestamp) / 1000 / 60));
    }
  } catch {
    console.log('Type: String');
    console.log('Value preview:', value.substring(0, 500));
  }

  console.groupEnd();
}

// Make functions available globally in dev
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  (window as any).analyzeStorage = analyzeStorage;
  (window as any).clearThreadCache = clearThreadCache;
  (window as any).clearAgentCache = clearAgentCache;
  (window as any).clearOldData = clearOldData;
  (window as any).clearByPattern = clearByPattern;
  (window as any).inspectKey = inspectKey;
}
