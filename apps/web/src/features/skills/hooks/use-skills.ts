"use client";

import { useState, useCallback, useEffect } from "react";
import { useAuthContext } from "@/providers/Auth";
import { toast } from "sonner";
import type {
  Skill,
  SkillListResponse,
  SkillPermission,
  SkillShareRequest,
  SkillShareResponse,
  SkillValidationResult,
} from "@/types/skill";

// Cache configuration
const SKILLS_CACHE_KEY = "oap_skills_cache_v1";
const SKILLS_CACHE_DURATION = 5 * 60 * 1000; // 5 minutes

interface SkillsCache {
  skills: Skill[];
  timestamp: number;
  userId: string;
}

/**
 * Hook for managing skills data and operations.
 */
export function useSkills() {
  const { user, session } = useAuthContext();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Get access token from session
  const accessToken = session?.accessToken;

  // Fetch headers
  const getHeaders = useCallback(() => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (accessToken) {
      headers["Authorization"] = `Bearer ${accessToken}`;
    }
    return headers;
  }, [accessToken]);

  // Load skills from cache
  const loadFromCache = useCallback((): SkillsCache | null => {
    try {
      const cached = localStorage.getItem(SKILLS_CACHE_KEY);
      if (cached) {
        const parsed = JSON.parse(cached) as SkillsCache;
        const now = Date.now();
        // Check if cache is still valid and belongs to current user
        if (
          now - parsed.timestamp < SKILLS_CACHE_DURATION &&
          parsed.userId === user?.id
        ) {
          return parsed;
        }
      }
    } catch (e) {
      console.warn("Failed to load skills cache:", e);
    }
    return null;
  }, [user?.id]);

  // Save skills to cache
  const saveToCache = useCallback(
    (skillsList: Skill[]) => {
      if (!user?.id) return;
      try {
        const cache: SkillsCache = {
          skills: skillsList,
          timestamp: Date.now(),
          userId: user.id,
        };
        localStorage.setItem(SKILLS_CACHE_KEY, JSON.stringify(cache));
      } catch (e) {
        console.warn("Failed to save skills cache:", e);
      }
    },
    [user?.id]
  );

  // Clear cache
  const clearCache = useCallback(() => {
    localStorage.removeItem(SKILLS_CACHE_KEY);
  }, []);

  // Fetch all accessible skills
  const fetchSkills = useCallback(
    async (force = false) => {
      if (!accessToken) {
        setIsLoading(false);
        return;
      }

      // Check cache first
      if (!force) {
        const cached = loadFromCache();
        if (cached) {
          setSkills(cached.skills);
          setIsLoading(false);
          return;
        }
      }

      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch("/api/langconnect/skills", {
          headers: getHeaders(),
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch skills: ${response.statusText}`);
        }

        const data: SkillListResponse = await response.json();
        setSkills(data.skills);
        saveToCache(data.skills);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setError(message);
        console.error("Error fetching skills:", err);
      } finally {
        setIsLoading(false);
      }
    },
    [accessToken, getHeaders, loadFromCache, saveToCache]
  );

  // Fetch a specific skill by ID
  const fetchSkill = useCallback(
    async (skillId: string): Promise<Skill | null> => {
      if (!accessToken) return null;

      try {
        const response = await fetch(`/api/langconnect/skills/${skillId}`, {
          headers: getHeaders(),
        });

        if (!response.ok) {
          throw new Error(`Failed to fetch skill: ${response.statusText}`);
        }

        return await response.json();
      } catch (err) {
        console.error("Error fetching skill:", err);
        return null;
      }
    },
    [accessToken, getHeaders]
  );

  // Validate a skill zip file
  const validateSkillZip = useCallback(
    async (file: File): Promise<SkillValidationResult> => {
      if (!accessToken) {
        return {
          valid: false,
          name: null,
          description: null,
          pip_requirements: null,
          files: [],
          errors: ["Not authenticated"],
        };
      }

      const formData = new FormData();
      formData.append("file", file);

      try {
        const response = await fetch("/api/langconnect/skills/validate", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
          body: formData,
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          return {
            valid: false,
            name: null,
            description: null,
            pip_requirements: null,
            files: [],
            errors: [errorData.detail || "Validation failed"],
          };
        }

        return await response.json();
      } catch (err) {
        return {
          valid: false,
          name: null,
          description: null,
          pip_requirements: null,
          files: [],
          errors: [err instanceof Error ? err.message : "Unknown error"],
        };
      }
    },
    [accessToken]
  );

  // Upload a new skill
  const uploadSkill = useCallback(
    async (file: File): Promise<Skill | null> => {
      if (!accessToken) {
        toast.error("Not authenticated");
        return null;
      }

      const formData = new FormData();
      formData.append("file", file);

      try {
        const response = await fetch("/api/langconnect/skills", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
          body: formData,
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMsg =
            errorData.detail?.message ||
            errorData.detail ||
            "Failed to upload skill";
          toast.error(errorMsg);
          return null;
        }

        const skill: Skill = await response.json();
        clearCache();
        await fetchSkills(true);
        toast.success(`Skill "${skill.name}" uploaded successfully`);
        return skill;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        toast.error(`Failed to upload skill: ${message}`);
        return null;
      }
    },
    [accessToken, clearCache, fetchSkills]
  );

  // Update an existing skill
  const updateSkill = useCallback(
    async (skillId: string, file: File): Promise<Skill | null> => {
      if (!accessToken) {
        toast.error("Not authenticated");
        return null;
      }

      const formData = new FormData();
      formData.append("file", file);

      try {
        const response = await fetch(`/api/langconnect/skills/${skillId}`, {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
          body: formData,
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMsg =
            errorData.detail?.message ||
            errorData.detail ||
            "Failed to update skill";
          toast.error(errorMsg);
          return null;
        }

        const skill: Skill = await response.json();
        clearCache();
        await fetchSkills(true);
        toast.success(`Skill "${skill.name}" updated successfully`);
        return skill;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        toast.error(`Failed to update skill: ${message}`);
        return null;
      }
    },
    [accessToken, clearCache, fetchSkills]
  );

  // Delete a skill
  const deleteSkill = useCallback(
    async (skillId: string): Promise<boolean> => {
      if (!accessToken) {
        toast.error("Not authenticated");
        return false;
      }

      try {
        const response = await fetch(`/api/langconnect/skills/${skillId}`, {
          method: "DELETE",
          headers: getHeaders(),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          toast.error(errorData.detail || "Failed to delete skill");
          return false;
        }

        clearCache();
        await fetchSkills(true);
        toast.success("Skill deleted successfully");
        return true;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        toast.error(`Failed to delete skill: ${message}`);
        return false;
      }
    },
    [accessToken, getHeaders, clearCache, fetchSkills]
  );

  // Share a skill with users
  const shareSkill = useCallback(
    async (
      skillId: string,
      shareRequest: SkillShareRequest
    ): Promise<SkillShareResponse | null> => {
      if (!accessToken) {
        toast.error("Not authenticated");
        return null;
      }

      try {
        const response = await fetch(
          `/api/langconnect/skills/${skillId}/share`,
          {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify(shareRequest),
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          toast.error(errorData.detail || "Failed to share skill");
          return null;
        }

        const result: SkillShareResponse = await response.json();

        if (result.success) {
          toast.success("Skill shared successfully");
        } else if (result.errors.length > 0) {
          toast.warning(`Shared with issues: ${result.errors.join(", ")}`);
        }

        return result;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        toast.error(`Failed to share skill: ${message}`);
        return null;
      }
    },
    [accessToken, getHeaders]
  );

  // Get skill permissions
  const getSkillPermissions = useCallback(
    async (skillId: string): Promise<SkillPermission[]> => {
      if (!accessToken) return [];

      try {
        const response = await fetch(
          `/api/langconnect/skills/${skillId}/permissions`,
          {
            headers: getHeaders(),
          }
        );

        if (!response.ok) {
          throw new Error("Failed to fetch permissions");
        }

        return await response.json();
      } catch (err) {
        console.error("Error fetching skill permissions:", err);
        return [];
      }
    },
    [accessToken, getHeaders]
  );

  // Revoke a user's permission
  const revokePermission = useCallback(
    async (skillId: string, userId: string): Promise<boolean> => {
      if (!accessToken) {
        toast.error("Not authenticated");
        return false;
      }

      try {
        const response = await fetch(
          `/api/langconnect/skills/${skillId}/permissions/${userId}`,
          {
            method: "DELETE",
            headers: getHeaders(),
          }
        );

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          toast.error(errorData.detail || "Failed to revoke permission");
          return false;
        }

        toast.success("Permission revoked successfully");
        return true;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        toast.error(`Failed to revoke permission: ${message}`);
        return false;
      }
    },
    [accessToken, getHeaders]
  );

  // Initial fetch
  useEffect(() => {
    if (accessToken) {
      fetchSkills();
    }
  }, [accessToken, fetchSkills]);

  return {
    skills,
    isLoading,
    error,
    fetchSkills,
    fetchSkill,
    validateSkillZip,
    uploadSkill,
    updateSkill,
    deleteSkill,
    shareSkill,
    getSkillPermissions,
    revokePermission,
    clearCache,
  };
}
