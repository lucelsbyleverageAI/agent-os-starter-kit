"use client";

import React, { useState, useCallback, useEffect } from "react";
import { Check, ChevronDown, Search, User, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { CollaborativeUser } from "@/types/user";
import { useUsers } from "@/hooks/use-users";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";

interface UserMultiSelectProps {
  selectedUsers: CollaborativeUser[];
  onUsersChange: (users: CollaborativeUser[]) => void;
  excludeUserIds?: string[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  maxUsers?: number;
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

export function UserMultiSelect({
  selectedUsers,
  onUsersChange,
  excludeUserIds = [],
  placeholder = "Search and select team members...",
  className,
  disabled = false,
  maxUsers,
}: UserMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const { users, searchUsers, searchResults, searchLoading, clearSearch } = useUsers();

  // Combine excluded user IDs with selected user IDs
  const allExcludedIds = [...excludeUserIds, ...selectedUsers.map(user => user.id)];
  
  // Filter available users based on search and exclusions
  const availableUsers = searchQuery.trim() 
    ? searchResults.filter(user => !allExcludedIds.includes(user.id))
    : users.filter(user => !allExcludedIds.includes(user.id));

  // Handle user selection
  const handleUserSelect = useCallback((user: CollaborativeUser) => {
    if (maxUsers && selectedUsers.length >= maxUsers) {
      return; // Don't allow selection if max users reached
    }
    
    const newSelectedUsers = [...selectedUsers, user];
    onUsersChange(newSelectedUsers);
  }, [selectedUsers, onUsersChange, maxUsers]);

  // Handle user removal
  const handleUserRemove = useCallback((userId: string) => {
    const newSelectedUsers = selectedUsers.filter(user => user.id !== userId);
    onUsersChange(newSelectedUsers);
  }, [selectedUsers, onUsersChange]);

  // Handle search with debouncing
  const handleSearch = useCallback(async (query: string) => {
    setSearchQuery(query);
    if (query.trim()) {
      await searchUsers(query, { exclude_user_ids: allExcludedIds });
    } else {
      clearSearch();
    }
  }, [searchUsers, clearSearch, allExcludedIds]);

  // Clear search when popover closes
  useEffect(() => {
    if (!open) {
      setSearchQuery("");
      clearSearch();
    }
  }, [open, clearSearch]);

  const isMaxUsersReached = maxUsers && selectedUsers.length >= maxUsers;

  return (
    <div className={cn("w-full", className)}>
      {/* Selected Users Display */}
      {selectedUsers.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {selectedUsers.map((user) => (
            <Badge
              key={user.id}
              variant="secondary"
              className="flex items-center gap-2 px-3 py-1"
            >
              {/* User Avatar */}
              <div className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt={getUserDisplayName(user)}
                    className="h-5 w-5 rounded-full"
                  />
                ) : (
                  <span>{getUserInitials(user)}</span>
                )}
              </div>
              
              {/* User Name */}
              <span className="text-sm">
                {getUserDisplayName(user)}
              </span>
              
              {/* Remove Button */}
              <Button
                variant="ghost"
                size="sm"
                className="h-4 w-4 p-0 hover:bg-destructive hover:text-destructive-foreground"
                onClick={() => handleUserRemove(user.id)}
                disabled={disabled}
              >
                <X className="h-3 w-3" />
              </Button>
            </Badge>
          ))}
        </div>
      )}

      {/* User Selection Popover */}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className={cn(
              "w-full justify-between",
              !selectedUsers.length && "text-muted-foreground"
            )}
            disabled={disabled || Boolean(isMaxUsersReached)}
          >
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4" />
              <span>
                {isMaxUsersReached 
                  ? `Maximum ${maxUsers} users selected`
                  : selectedUsers.length > 0 
                    ? `${selectedUsers.length} user${selectedUsers.length === 1 ? '' : 's'} selected`
                    : placeholder
                }
              </span>
            </div>
            <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        
        <PopoverContent className="w-full p-0" side="bottom" align="start">
          <Command>
            <CommandInput
              placeholder="Search users..."
              value={searchQuery}
              onValueChange={handleSearch}
            />
            <CommandList className={cn("max-h-[300px]", ...getScrollbarClasses('y'))}>
              <CommandEmpty>
                {searchLoading ? (
                  <div className="flex items-center justify-center py-6">
                    <div className="flex flex-col items-center gap-2">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-4 w-24" />
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col items-center py-6 text-sm text-muted-foreground">
                    <User className="mb-2 h-8 w-8" />
                    <p>No users found</p>
                    {searchQuery && (
                      <p className="text-xs">Try a different search term</p>
                    )}
                  </div>
                )}
              </CommandEmpty>
              
              {availableUsers.length > 0 && (
                <CommandGroup>
                  {availableUsers.map((user) => (
                    <CommandItem
                      key={user.id}
                      value={user.id}
                      onSelect={() => handleUserSelect(user)}
                      className="flex items-center gap-3 p-3"
                      disabled={Boolean(isMaxUsersReached)}
                    >
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
                      
                      {/* User Info */}
                      <div className="flex flex-1 flex-col">
                        <span className="text-sm font-medium">
                          {getUserDisplayName(user)}
                        </span>
                        {(user.display_name || user.first_name || user.last_name) && (
                          <span className="text-xs text-muted-foreground">
                            {user.email}
                          </span>
                        )}
                      </div>
                      
                      {/* Selection Indicator */}
                      <div className="flex h-4 w-4 items-center justify-center rounded border">
                        {selectedUsers.some(u => u.id === user.id) && (
                          <Check className="h-3 w-3" />
                        )}
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      
      {/* Helper Text */}
      {maxUsers && (
        <p className="mt-2 text-xs text-muted-foreground">
          {selectedUsers.length} user{selectedUsers.length === 1 ? '' : 's'} selected (max {maxUsers})
        </p>
      )}
    </div>
  );
} 