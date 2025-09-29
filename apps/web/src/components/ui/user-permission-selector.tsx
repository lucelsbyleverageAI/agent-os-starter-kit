"use client";

import React from "react";
import { X, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CollaborativeUser } from "@/types/user";

interface UserPermissionSelectorProps {
  users: CollaborativeUser[];
  permissions: Record<string, 'editor' | 'viewer'>;
  onPermissionsChange: (permissions: Record<string, 'editor' | 'viewer'>) => void;
  onRemoveUser?: (userId: string) => void;
  className?: string;
  disabled?: boolean;
  showBulkActions?: boolean;
}

// Helper function to get user display name
const getUserDisplayName = (user: CollaborativeUser): string => {
  if (user.display_name) return user.display_name;
  if (user.first_name && user.last_name) {
    return `${user.first_name} ${user.last_name}`;
  }
  return user.email;
};

// Helper function to get user initials for avatar
const getUserInitials = (user: CollaborativeUser): string => {
  if (user.first_name && user.last_name) {
    return `${user.first_name[0]}${user.last_name[0]}`.toUpperCase();
  }
  if (user.display_name) {
    const parts = user.display_name.split(' ');
    if (parts.length > 1) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return user.display_name.slice(0, 2).toUpperCase();
  }
  return user.email.slice(0, 2).toUpperCase();
};

export function UserPermissionSelector({
  users,
  permissions,
  onPermissionsChange,
  onRemoveUser,
  className,
  disabled = false,
  showBulkActions = true,
}: UserPermissionSelectorProps) {
  
  // Handle individual permission change
  const handlePermissionChange = (userId: string, permission: 'editor' | 'viewer') => {
    const newPermissions = { ...permissions, [userId]: permission };
    onPermissionsChange(newPermissions);
  };

  // Handle bulk permission changes
  const handleBulkPermissionChange = (permission: 'editor' | 'viewer') => {
    const newPermissions = { ...permissions };
    users.forEach(user => {
      newPermissions[user.id] = permission;
    });
    onPermissionsChange(newPermissions);
  };

  // Count permission types
  const editorCount = Object.values(permissions).filter(p => p === 'editor').length;
  const viewerCount = Object.values(permissions).filter(p => p === 'viewer').length;

  if (users.length === 0) {
    return (
      <div className={cn("flex flex-col items-center justify-center py-6 text-center", className)}>
        <Users className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">No users selected</p>
        <p className="text-xs text-muted-foreground">Select users to assign permissions</p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      {/* Summary and Bulk Actions */}
      {showBulkActions && users.length > 1 && (
        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="flex items-center gap-4">
            <div className="text-sm">
              <span className="font-medium">{users.length} users selected</span>
              <div className="flex gap-3 text-xs text-muted-foreground">
                <span>{editorCount} editors</span>
                <span>{viewerCount} viewers</span>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Set all to:</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleBulkPermissionChange('editor')}
              disabled={disabled}
            >
              Editor
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleBulkPermissionChange('viewer')}
              disabled={disabled}
            >
              Viewer
            </Button>
          </div>
        </div>
      )}

      {/* Individual User Permissions */}
      <div className="space-y-2">
        {users.map((user) => (
          <div
            key={user.id}
            className="flex items-center justify-between rounded-lg border p-3"
          >
            {/* User Info */}
            <div className="flex items-center gap-3">
              {/* User Avatar */}
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-sm">
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={getUserDisplayName(user)}
                    className="h-8 w-8 rounded-full"
                  />
                ) : (
                  <span>{getUserInitials(user)}</span>
                )}
              </div>
              
              {/* User Details */}
              <div className="flex flex-col">
                <span className="text-sm font-medium">
                  {getUserDisplayName(user)}
                </span>
                {(user.display_name || user.first_name) && (
                  <span className="text-xs text-muted-foreground">
                    {user.email}
                  </span>
                )}
              </div>
            </div>

            {/* Permission Controls */}
            <div className="flex items-center gap-2">
              {/* Permission Selector */}
              <Select
                value={permissions[user.id] || 'viewer'}
                onValueChange={(value: 'editor' | 'viewer') => 
                  handlePermissionChange(user.id, value)
                }
                disabled={disabled}
              >
                <SelectTrigger className="w-24">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="editor">
                    <div className="flex flex-col">
                      <span>Editor</span>
                      <span className="text-xs text-muted-foreground">
                        Can add and edit documents
                      </span>
                    </div>
                  </SelectItem>
                  <SelectItem value="viewer">
                    <div className="flex flex-col">
                      <span>Viewer</span>
                      <span className="text-xs text-muted-foreground">
                        Can view documents only
                      </span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>

              {/* Remove User Button */}
              {onRemoveUser && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0 text-muted-foreground hover:bg-destructive hover:text-destructive-foreground"
                  onClick={() => onRemoveUser(user.id)}
                  disabled={disabled}
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Permission Legend */}
      <div className="rounded-lg bg-muted/50 p-3">
        <h4 className="mb-2 text-sm font-medium">Permission Levels</h4>
        <div className="space-y-1 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="px-2 py-0 text-xs">
              Editor
            </Badge>
            <span>Can view, add, edit, and delete documents in this collection</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="px-2 py-0 text-xs">
              Viewer
            </Badge>
            <span>Can view documents but cannot make changes</span>
          </div>
        </div>
      </div>
    </div>
  );
} 