// Collaborative user types extending the basic auth types
export interface CollaborativeUser {
  id: string;
  email: string;
  display_name?: string;
  first_name?: string;
  last_name?: string;
  avatar_url?: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ShareAtCreation {
  user_id: string;
  permission_level: 'editor' | 'viewer';
}

export interface ShareRequest {
  user_id: string;
  permission_level: 'editor' | 'viewer';
}

export interface Permission {
  id: string;
  collection_id: string;
  user_id: string;
  permission_level: 'owner' | 'editor' | 'viewer';
  granted_by: string;
  created_at: string;
}

export interface UserPermission {
  user: CollaborativeUser;
  permission_level: 'owner' | 'editor' | 'viewer';
  granted_by: string;
  granted_at: string;
}

// Helper type for user selection in UI
export interface SelectableUser extends CollaborativeUser {
  isSelected?: boolean;
}

// Type for user search and filtering
export interface UserSearchOptions {
  query?: string;
  exclude_user_ids?: string[];
  limit?: number;
  offset?: number;
}

// API response types
export interface UsersResponse {
  users: CollaborativeUser[];
  total: number;
  has_more: boolean;
}

export interface UserSearchResponse {
  users: CollaborativeUser[];
  total: number;
} 