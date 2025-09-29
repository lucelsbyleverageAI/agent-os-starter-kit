import { ShareAtCreation, UserPermission } from './user';

export type Collection = {
  name: string;
  uuid: string;
  metadata: {
    description?: string;
    [key: string]: any;
  };
  // New collaborative fields
  permission_level?: 'owner' | 'editor' | 'viewer';
  owner_id?: string;
  shared_with?: UserPermission[];
  is_shared?: boolean;
  shared_count?: number;
  // Document count
  document_count?: number;
};

export type CollectionCreate = {
  name: string;
  metadata: Record<string, any>;
  share_with?: ShareAtCreation[];
};

export type CollectionUpdate = {
  name?: string;
  metadata?: Record<string, any>;
};

export type CollectionWithPermissions = Collection & {
  permissions: UserPermission[];
};
