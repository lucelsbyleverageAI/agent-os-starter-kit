export interface PublicPermission {
  id: number;
  permission_level: string;
  created_at: string | null;
  revoked_at: string | null;
  revoke_mode: string | null;
  notes: string | null;
  created_by: string;
}

export interface PublicGraphPermission extends PublicPermission {
  graph_id: string;
  graph_display_name?: string; // To be enriched on the frontend
}

export interface PublicAssistantPermission extends PublicPermission {
  assistant_id: string;
  assistant_display_name?: string; // To be enriched on the frontend
}

export interface PublicCollectionPermission extends PublicPermission {
  collection_id: string;
  collection_display_name?: string; // To be enriched on the frontend
} 