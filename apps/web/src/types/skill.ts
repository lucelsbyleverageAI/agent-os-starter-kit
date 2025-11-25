/**
 * Skill types for the Skills feature.
 *
 * Skills are modular capability packages that extend agent functionality
 * through filesystem-based instructions, scripts, and resources.
 */

export type SkillPermissionLevel = "owner" | "editor" | "viewer";

export interface Skill {
  id: string;
  name: string;
  description: string;
  storage_path: string;
  pip_requirements: string[] | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  permission_level: SkillPermissionLevel | null;
  is_public: boolean;
}

export interface SkillListResponse {
  skills: Skill[];
  total: number;
}

export interface SkillPermission {
  id: string;
  skill_id: string;
  user_id: string;
  permission_level: SkillPermissionLevel;
  granted_by: string;
  created_at: string;
  updated_at: string;
  user_email?: string;
  user_display_name?: string;
}

export interface SkillShareRequest {
  users: Array<{
    user_id: string;
    permission_level: SkillPermissionLevel;
  }>;
}

export interface SkillShareResponse {
  success: boolean;
  shared_with: SkillPermission[];
  errors: string[];
}

export interface SkillValidationResult {
  valid: boolean;
  name: string | null;
  description: string | null;
  pip_requirements: string[] | null;
  files: string[];
  errors: string[];
}

/**
 * Skill reference for agent configuration.
 * This is the lightweight reference stored in agent config.
 */
export interface SkillReference {
  skill_id: string;
  name: string;
  description: string;
}

/**
 * Skills configuration for an agent.
 */
export interface SkillsConfig {
  skills: SkillReference[];
}
