'use client';

import { useEffect } from 'react';

/**
 * Loads debug utilities in development mode
 * Makes storage analysis tools available in browser console
 */
export function ClientDebugTools() {
  useEffect(() => {
    if (process.env.NODE_ENV === 'development') {
      // Dynamically import debug tools
      import('@/lib/debug-storage').then((module) => {
        // Make functions globally available
        (window as any).analyzeStorage = module.analyzeStorage;
        (window as any).clearThreadCache = module.clearThreadCache;
        (window as any).clearAgentCache = module.clearAgentCache;
        (window as any).clearOldData = module.clearOldData;
        (window as any).clearByPattern = module.clearByPattern;
        (window as any).inspectKey = module.inspectKey;

        console.log('🛠️ Debug tools loaded! Available commands:');
        console.log('  analyzeStorage()        - Analyze localStorage usage');
        console.log('  clearThreadCache()      - Clear thread message caches');
        console.log('  clearAgentCache()       - Clear agent config caches');
        console.log('  clearOldData()          - Clear all caches (keep auth)');
        console.log('  clearByPattern("text")  - Clear keys matching pattern');
        console.log('  inspectKey("key")       - Inspect specific key');
      });
    }
  }, []);

  return null;
}
