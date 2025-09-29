"use client";

import { Edit, Eye, X } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { CollaborativeUser } from "@/types/user";
import { cn } from "@/lib/utils";

interface PermissionAssignmentTableProps {
  selectedUsers: CollaborativeUser[];
  userPermissions: Record<string, 'editor' | 'viewer'>;
  onPermissionChange: (userId: string, permission: 'editor' | 'viewer') => void;
  onRemoveUser: (userId: string) => void;
  className?: string;
}

// Helper function to get user display name with proper fallbacks
const getUserDisplayName = (user: CollaborativeUser): string => {
  if (user.display_name?.trim()) {
    return user.display_name.trim();
  }
  
  const fullName = `${user.first_name || ''} ${user.last_name || ''}`.trim();
  if (fullName) {
    return fullName;
  }
  
  return user.email;
};

// Helper function to get user initials
const getUserInitials = (user: CollaborativeUser): string => {
  if (user.display_name?.trim()) {
    return user.display_name.trim().slice(0, 2).toUpperCase();
  }
  
  if (user.first_name?.trim() && user.last_name?.trim()) {
    return `${user.first_name[0]}${user.last_name[0]}`.toUpperCase();
  }
  
  if (user.first_name?.trim()) {
    return user.first_name.slice(0, 2).toUpperCase();
  }
  
  return user.email.slice(0, 2).toUpperCase();
};

export function PermissionAssignmentTable({
  selectedUsers,
  userPermissions,
  onPermissionChange,
  onRemoveUser,
  className,
}: PermissionAssignmentTableProps) {
  if (selectedUsers.length === 0) {
    return null;
  }

  return (
    <div className={cn("space-y-3", className)}>
      <h5 className="text-sm font-medium">Permission Levels</h5>
      <div className="border rounded-lg bg-muted/25">
        <div className="p-3 space-y-2">
          {selectedUsers.map((user) => {
            const userPermission = userPermissions[user.id] || 'viewer';
            
            return (
              <div key={user.id} className="flex items-center justify-between gap-3 py-2">
                {/* User Info */}
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <Avatar className="h-5 w-5 shrink-0">
                    <AvatarFallback className="text-xs">
                      {getUserInitials(user)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">
                      {getUserDisplayName(user)}
                    </p>
                  </div>
                </div>
                
                {/* Permission Controls */}
                <div className="flex items-center gap-1 shrink-0">
                  <Button
                    variant={userPermission === 'viewer' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => onPermissionChange(user.id, 'viewer')}
                    className="h-7 px-2 text-xs"
                  >
                    <Eye className="h-3 w-3 mr-1" />
                    Viewer
                  </Button>
                  <Button
                    variant={userPermission === 'editor' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => onPermissionChange(user.id, 'editor')}
                    className="h-7 px-2 text-xs"
                  >
                    <Edit className="h-3 w-3 mr-1" />
                    Editor
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onRemoveUser(user.id)}
                    className="h-7 w-7 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
                  >
                    <X className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
} 