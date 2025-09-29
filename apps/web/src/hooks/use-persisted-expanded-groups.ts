import { useState, useEffect } from "react";

const STORAGE_KEY = "sidebar-chat-history-expanded";
const DEFAULT_EXPANDED = ["Today", "Yesterday", "Previous 7 Days"];

/**
 * Custom hook to persist expanded groups state in localStorage
 * with proper SSR handling and fallback behavior
 */
export function usePersistedExpandedGroups() {
  const [expandedGroups, setExpandedGroupsState] = useState<Set<string>>(
    new Set(DEFAULT_EXPANDED)
  );
  const [isHydrated, setIsHydrated] = useState(false);

  // Load from localStorage on client-side hydration
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsedGroups = JSON.parse(stored);
        if (Array.isArray(parsedGroups)) {
          setExpandedGroupsState(new Set(parsedGroups));
        }
      }
    } catch (error) {
      console.warn("Failed to load expanded groups from localStorage:", error);
      // Keep default state on error
    } finally {
      setIsHydrated(true);
    }
  }, []);

  // Save to localStorage whenever state changes (but only after hydration)
  const setExpandedGroups = (newGroups: Set<string>) => {
    setExpandedGroupsState(newGroups);
    
    if (isHydrated) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(newGroups)));
      } catch (error) {
        console.warn("Failed to save expanded groups to localStorage:", error);
      }
    }
  };

  return [expandedGroups, setExpandedGroups] as const;
} 