"use client";

import React from "react";
import { Crown, Edit, Eye, UserX } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { TooltipIconButton } from "@/components/ui/tooltip-icon-button";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";

interface User {
  userId: string;
  name: string;
  email: string;
  initials: string;
  isCurrentUser?: boolean;
  canRemove?: boolean;
  permissionLevel: 'owner' | 'editor' | 'viewer';
}

interface UserPermissionsTableProps {
  users: User[];
  onRemoveUser?: (userId: string, userName: string) => void;
  className?: string;
  emptyState?: React.ReactNode;
}

const getPermissionIcon = (level: 'owner' | 'editor' | 'viewer') => {
  switch (level) {
    case 'owner':
      return Crown;
    case 'editor':
      return Edit;
    case 'viewer':
      return Eye;
    default:
      return Eye;
  }
};

const getPermissionLabel = (level: 'owner' | 'editor' | 'viewer') => {
  switch (level) {
    case 'owner':
      return 'Owner';
    case 'editor':
      return 'Editor';
    case 'viewer':
      return 'Viewer';
    default:
      return 'Viewer';
  }
};

const getPermissionVariant = (level: 'owner' | 'editor' | 'viewer') => {
  switch (level) {
    case 'owner':
      return 'default';
    case 'editor':
      return 'secondary';
    case 'viewer':
      return 'outline';
    default:
      return 'outline';
  }
};

export function UserPermissionsTable({
  users,
  onRemoveUser,
  className,
  emptyState,
}: UserPermissionsTableProps) {
  if (users.length === 0) {
    return emptyState || (
      <div className="text-center py-8 text-sm text-muted-foreground">
        No users have been granted access yet.
      </div>
    );
  }

  return (
    <div 
      className={cn(
        "max-h-80 space-y-2",
        users.length > 5 && "overflow-y-auto",
        users.length > 5 && getScrollbarClasses('y'),
        className
      )}
    >
      {users.map((user) => {
        const PermissionIcon = getPermissionIcon(user.permissionLevel);
        
        return (
          <div
            key={user.userId}
            className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-muted/50 transition-colors"
          >
            {/* User Info */}
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <Avatar className="h-8 w-8 flex-shrink-0">
                <AvatarFallback className="text-xs font-medium">
                  {user.initials}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <div className="font-medium text-sm truncate">
                  {user.name}
                  {user.isCurrentUser && (
                    <span className="text-muted-foreground ml-1">(You)</span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground truncate">
                  {user.email}
                </div>
              </div>
            </div>

            {/* Permission Badge and Remove Button */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <Badge variant={getPermissionVariant(user.permissionLevel)} className="flex items-center gap-1.5">
                <PermissionIcon className="h-3.5 w-3.5" />
                <span>{getPermissionLabel(user.permissionLevel)}</span>
              </Badge>

              {/* Remove Button */}
              {user.canRemove && onRemoveUser && (
                <TooltipIconButton
                  tooltip="Remove access"
                  onClick={() => onRemoveUser(user.userId, user.name)}
                  variant="ghost"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                >
                  <UserX className="h-4 w-4" />
                </TooltipIconButton>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
} 