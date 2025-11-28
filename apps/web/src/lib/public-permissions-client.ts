import { PublicAssistantPermission, PublicGraphPermission, PublicCollectionPermission, PublicSkillPermission } from "@/types/public-permissions";
import { Collection } from "@/types/collection";
import { Skill } from "@/types/skill";

export interface RevokePublicPermissionParams {
  id: string;
  accessToken: string;
  revokeMode: 'revoke_all' | 'future_only';
}

export interface CreatePublicGraphParams {
  graphId: string;
  permissionLevel: 'access' | 'admin';
  accessToken: string;
  notes?: string;
}

export interface CreatePublicAssistantParams {
  assistantId: string;
  permissionLevel: 'viewer' | 'editor';
  accessToken: string;
  notes?: string;
}

export interface CreatePublicCollectionParams {
  collectionId: string;
  permissionLevel: 'viewer' | 'editor';
  accessToken: string;
  notes?: string;
}

export interface CreatePublicSkillParams {
  skillId: string;
  permissionLevel: 'viewer' | 'editor';
  accessToken: string;
  notes?: string;
}

/**
 * Fetches all public graphs
 */
export const getPublicGraphs = async (accessToken: string): Promise<PublicGraphPermission[]> => {
  const response = await fetch("/api/langconnect/public-permissions/graphs", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    throw new Error("Failed to fetch public graphs");
  }
  return response.json();
};

/**
 * Creates a new public graph permission
 */
export const createPublicGraph = async (params: CreatePublicGraphParams) => {
  const response = await fetch("/api/langconnect/public-permissions/graphs", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${params.accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      graph_id: params.graphId,
      permission_level: params.permissionLevel,
      notes: params.notes,
    }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to create public graph permission");
  }
  return response.json();
};

/**
 * Fetches all public assistants
 */
export const getPublicAssistants = async (accessToken: string): Promise<PublicAssistantPermission[]> => {
  const response = await fetch("/api/langconnect/public-permissions/assistants", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    throw new Error("Failed to fetch public assistants");
  }
  return response.json();
};

/**
 * Creates a new public assistant permission
 */
export const createPublicAssistant = async (params: CreatePublicAssistantParams) => {
  const response = await fetch("/api/langconnect/public-permissions/assistants", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${params.accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      assistant_id: params.assistantId,
      permission_level: params.permissionLevel,
      notes: params.notes,
    }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to create public assistant permission");
  }
  return response.json();
};

/**
 * Revokes a public graph permission
 */
export const revokePublicGraph = async ({ id, accessToken, revokeMode }: RevokePublicPermissionParams): Promise<any> => {
  const response = await fetch(`/api/langconnect/public-permissions/graphs/${id}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ revoke_mode: revokeMode }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to revoke public graph permission' }));
    throw new Error(errorData.detail);
  }
  return response.json();
};

/**
 * Revokes a public assistant permission
 */
export const revokePublicAssistant = async ({ id, accessToken, revokeMode }: RevokePublicPermissionParams): Promise<any> => {
  const response = await fetch(`/api/langconnect/public-permissions/assistants/${id}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ revoke_mode: revokeMode }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to revoke public assistant permission' }));
    throw new Error(errorData.detail);
  }
  return response.json();
};

export async function reinvokePublicGraph({ graphId, accessToken }: { graphId: string; accessToken: string }) {
  const response = await fetch(`/api/langconnect/public-permissions/graphs/${graphId}/re-invoke`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || 'Failed to re-invoke public graph permission');
  }

  return response.json();
}

export async function reinvokePublicAssistant({ assistantId, accessToken }: { assistantId: string; accessToken: string }) {
  const response = await fetch(`/api/langconnect/public-permissions/assistants/${assistantId}/re-invoke`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || 'Failed to re-invoke public assistant permission');
  }

  return response.json();
}

// ============================================================================
// COLLECTION FUNCTIONS
// ============================================================================

/**
 * Fetches all public collections
 */
export const getPublicCollections = async (accessToken: string): Promise<PublicCollectionPermission[]> => {
  const response = await fetch("/api/langconnect/public-permissions/collections", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    throw new Error("Failed to fetch public collections");
  }
  return response.json();
};

/**
 * Creates a new public collection permission
 */
export const createPublicCollection = async (params: CreatePublicCollectionParams) => {
  const response = await fetch("/api/langconnect/public-permissions/collections", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${params.accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      collection_id: params.collectionId,
      permission_level: params.permissionLevel,
      notes: params.notes,
    }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to create public collection permission");
  }
  return response.json();
};

/**
 * Revokes a public collection permission
 */
export const revokePublicCollection = async ({ id, accessToken, revokeMode }: RevokePublicPermissionParams): Promise<any> => {
  const response = await fetch(`/api/langconnect/public-permissions/collections/${id}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ revoke_mode: revokeMode }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to revoke public collection permission' }));
    throw new Error(errorData.detail);
  }
  return response.json();
};

/**
 * Re-invokes a public collection permission
 */
export async function reinvokePublicCollection({ collectionId, accessToken }: { collectionId: string; accessToken: string }) {
  const response = await fetch(`/api/langconnect/public-permissions/collections/${collectionId}/re-invoke`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || 'Failed to re-invoke public collection permission');
  }

  return response.json();
}

// ============================================
// Admin Collections Endpoints
// ============================================

/**
 * Get all collections for admin dashboard (requires dev_admin role)
 */
export async function getAllCollectionsForAdmin(accessToken: string): Promise<Collection[]> {
  const response = await fetch('/api/langconnect/collections/admin/all', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`,
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch all collections: ${response.statusText}`);
  }

  return response.json();
}

// ============================================================================
// SKILL FUNCTIONS
// ============================================================================

/**
 * Fetches all public skills
 */
export const getPublicSkills = async (accessToken: string): Promise<PublicSkillPermission[]> => {
  const response = await fetch("/api/langconnect/public-permissions/skills", {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    throw new Error("Failed to fetch public skills");
  }
  return response.json();
};

/**
 * Creates a new public skill permission
 */
export const createPublicSkill = async (params: CreatePublicSkillParams) => {
  const response = await fetch("/api/langconnect/public-permissions/skills", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${params.accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      skill_id: params.skillId,
      permission_level: params.permissionLevel,
      notes: params.notes,
    }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to create public skill permission");
  }
  return response.json();
};

/**
 * Revokes a public skill permission
 */
export const revokePublicSkill = async ({ id, accessToken, revokeMode }: RevokePublicPermissionParams): Promise<any> => {
  const response = await fetch(`/api/langconnect/public-permissions/skills/${id}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ revoke_mode: revokeMode }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to revoke public skill permission' }));
    throw new Error(errorData.detail);
  }
  return response.json();
};

/**
 * Re-invokes a public skill permission
 */
export async function reinvokePublicSkill({ skillId, accessToken }: { skillId: string; accessToken: string }) {
  const response = await fetch(`/api/langconnect/public-permissions/skills/${skillId}/re-invoke`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || 'Failed to re-invoke public skill permission');
  }

  return response.json();
}

/**
 * Get all skills for admin dashboard (requires dev_admin role)
 */
export async function getAllSkillsForAdmin(accessToken: string): Promise<Skill[]> {
  const response = await fetch('/api/langconnect/skills', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`,
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch all skills: ${response.statusText}`);
  }

  const data = await response.json();
  return data.skills || [];
} 