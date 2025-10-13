"use client";

import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { toast } from 'sonner';
import { Crown, Shield, UserPlus, Loader2, Users } from 'lucide-react';
import { CollaborativeUser } from '@/types/user';
import { UserMultiSelect } from '@/components/ui/user-multi-select';
import { UserPermissionsTable } from '@/components/ui/user-permissions-table';
import { useAuthContext } from "@/providers/Auth";
import { useUsers } from "@/hooks/use-users";
import { useGraphPermissions } from "@/hooks/use-graph-permissions";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { Separator } from "@/components/ui/separator";
import { logger } from "@/lib/logger";

interface GraphPermissionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  graphId: string;
  graphName: string;
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

export function GraphPermissionsDialog({ open, onOpenChange, graphId, graphName }: GraphPermissionsDialogProps) {
  const { user, session } = useAuthContext();
  const { getUsersByIds } = useUsers();
  const { 
    permissions, 
    fetchPermissions, 
    grantPermissions, 
    revokePermission,
    loading 
  } = useGraphPermissions();
  
  const [showAddUsers, setShowAddUsers] = useState(false);
  const [selectedUsers, setSelectedUsers] = useState<CollaborativeUser[]>([]);
  const [userPermissions, setUserPermissions] = useState<Record<string, 'admin' | 'access'>>({});
  const [submitting, setSubmitting] = useState(false);
  const [userDetails, setUserDetails] = useState<CollaborativeUser[]>([]);
  const [userDetailsLoading, setUserDetailsLoading] = useState(false);
  const [showRemoveUserConfirmation, setShowRemoveUserConfirmation] = useState(false);
  const [userToRemove, setUserToRemove] = useState<{ id: string; name: string } | null>(null);

  // Create user details map from loaded user details
  const userDetailsMap = userDetails.reduce((acc, user) => {
    acc[user.id] = user;
    return acc;
  }, {} as Record<string, CollaborativeUser>);

  // Load user details whenever permissions change
  useEffect(() => {
    const loadUserDetails = async () => {
      if (permissions.length === 0) {
        setUserDetails([]);
        setUserDetailsLoading(false);
        return;
      }

      setUserDetailsLoading(true);
      try {
        const userIds = permissions.map(p => p.user_id);
        const fetchedUserDetails = await getUsersByIds(userIds);
        setUserDetails(fetchedUserDetails);
                
        // Warn if we didn't get all user details
        if (fetchedUserDetails.length < userIds.length) {
          const missingIds = userIds.filter(id => !fetchedUserDetails.find(u => u.id === id));
          logger.warn(`Missing user details for:`, missingIds);
        }
      } catch (error) {
        logger.error('Failed to load user details:', error);
        // Keep existing user details on error rather than clearing
        // setUserDetails([]);
      } finally {
        setUserDetailsLoading(false);
      }
    };

    // Only load user details if we have permissions but not loading permissions
    if (!loading) {
      loadUserDetails();
    }
  }, [permissions, getUsersByIds, loading]);

  // Transform permissions data for UserPermissionsTable
  const transformedUsers = permissions.map((permission) => {
    const userDetail = userDetailsMap[permission.user_id];
    const isCurrentUser = permission.user_id === user?.id;
    const canRemove = permission.permission_level !== 'admin' || permissions.filter(p => p.permission_level === 'admin').length > 1;
    
    if (userDetail) {
      return {
        userId: permission.user_id,
        name: getUserDisplayName(userDetail),
        email: userDetail.email,
        initials: getUserInitials(userDetail),
        isCurrentUser,
        canRemove: canRemove && !isCurrentUser,
        permissionLevel: permission.permission_level === 'admin' ? 'owner' as const : 'viewer' as const
      };
    } else {
      // Fallback for missing user details
      return {
        userId: permission.user_id,
        name: permission.user_id,
        email: permission.user_id,
        initials: permission.user_id.slice(0, 2).toUpperCase(),
        isCurrentUser,
        canRemove: canRemove && !isCurrentUser,
        permissionLevel: permission.permission_level === 'admin' ? 'owner' as const : 'viewer' as const
      };
    }
  });

  // Fetch permissions when dialog opens
  useEffect(() => {
    if (open && graphId) {
      fetchPermissions(graphId);
    }
  }, [open, graphId, fetchPermissions]);

  // Add new users
  const handleAddUsers = async () => {
    if (!session?.accessToken) {
      toast.error('Authentication required');
      return;
    }

    const permissionsArray = Object.entries(userPermissions).map(([userId, permissionLevel]) => ({
      user_id: userId,
      permission_level: permissionLevel,
    }));

    if (permissionsArray.length === 0) {
      toast.error('Please select users and permissions');
      return;
    }

    setSubmitting(true);
    try {
      const result = await grantPermissions(graphId, permissionsArray);
      
      if (result.success) {
        toast.success(`Granted access to ${permissionsArray.length} user${permissionsArray.length > 1 ? 's' : ''}`);
        setShowAddUsers(false);
        setSelectedUsers([]);
        setUserPermissions({});
        // Permissions will be refreshed by the grantPermissions function
        // User details will be automatically reloaded via the useEffect above
      } else if (result.errors && result.errors.length > 0) {
        toast.error(`Some grants failed: ${result.errors.join(', ')}`);
      }
    } catch (error) {
      logger.error('Error granting graph permissions:', error);
      toast.error('Failed to grant permissions');
    } finally {
      setSubmitting(false);
    }
  };

  // Remove user permission
  const handleRemoveUser = async (userId: string, userName: string) => {
    setUserToRemove({ id: userId, name: userName });
    setShowRemoveUserConfirmation(true);
  };

  const confirmRemoveUser = async () => {
    if (!userToRemove || !session?.accessToken) return;

    setShowRemoveUserConfirmation(false);

    try {
      await revokePermission(graphId, userToRemove.id);
      toast.success(`Removed ${userToRemove.name}'s access`);
      // Permissions will be refreshed by the revokePermission function
      // User details will be automatically reloaded via the useEffect above
    } catch (error) {
      logger.error('Error removing user:', error);
      toast.error('Failed to remove user access');
    } finally {
      setUserToRemove(null);
    }
  };

  // Smart exclude logic: exclude current user AND users who already have access
  const excludeUserIds = [
    ...(user?.id ? [user.id] : []), // Exclude current user
    ...permissions.map(p => p.user_id) // Exclude users who already have access
  ];

  // Update permissions when selectedUsers change
  useEffect(() => {
    const newPermissions: Record<string, 'admin' | 'access'> = {};
    selectedUsers.forEach(user => {
      // Default to access if not already set
      newPermissions[user.id] = userPermissions[user.id] || 'access';
    });
    setUserPermissions(newPermissions);
  }, [selectedUsers]);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader className="pb-4">
            <DialogTitle>Manage Template Access</DialogTitle>
            <DialogDescription>
              Control who has access to the "{graphName}" template and their permission levels.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6">
            <Separator />

            <div className="space-y-4">
              {/* Current Permissions */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-sm font-medium">
                    Current Access {permissions.length > 0 && (
                      <span className="text-muted-foreground">({permissions.length} user{permissions.length !== 1 ? 's' : ''})</span>
                    )}
                  </h4>
                  {!showAddUsers && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowAddUsers(true)}
                      className="flex items-center gap-2"
                    >
                      <UserPlus className="h-4 w-4" />
                      Add Users
                    </Button>
                  )}
                </div>

                {loading || userDetailsLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin" />
                    <span className="ml-2 text-sm text-muted-foreground">
                      {loading ? "Loading permissions..." : "Loading user details..."}
                    </span>
                  </div>
                ) : (
                  <UserPermissionsTable
                    users={transformedUsers}
                    onRemoveUser={handleRemoveUser}
                    className="border rounded-lg p-2"
                    emptyState={
                      <div className="text-center py-8 text-sm text-muted-foreground">
                        <Users className="h-8 w-8 mx-auto mb-3 opacity-50" />
                        <p>No users have access to this template</p>
                        <p className="text-xs mt-1">Add team members to start collaborating</p>
                      </div>
                    }
                  />
                )}
              </div>

              {/* Add New Users Section */}
              {showAddUsers && (
                <div className="border-t pt-4">
                  <h4 className="text-sm font-medium mb-3">Add New Users</h4>
                  <div className="space-y-4">
                    <UserMultiSelect
                      selectedUsers={selectedUsers}
                      onUsersChange={setSelectedUsers}
                      excludeUserIds={excludeUserIds}
                      maxUsers={10}
                      placeholder="Search for team members to grant access..."
                    />
                    
                    {selectedUsers.length > 0 && (
                      <div className="space-y-3">
                        <h5 className="text-sm font-medium">Permission Levels</h5>
                        <div className="border rounded-lg bg-muted/25">
                          <div className="p-3 space-y-2">
                            {selectedUsers.map((selectedUser) => (
                              <div key={selectedUser.id} className="flex items-center justify-between gap-3 py-2">
                                {/* User Info */}
                                <div className="flex items-center gap-2 min-w-0 flex-1">
                                  <Avatar className="h-5 w-5 shrink-0">
                                    <AvatarFallback className="text-xs">
                                      {getUserInitials(selectedUser)}
                                    </AvatarFallback>
                                  </Avatar>
                                  <div className="min-w-0 flex-1">
                                    <p className="text-sm font-medium truncate">
                                      {getUserDisplayName(selectedUser)}
                                    </p>
                                  </div>
                                </div>
                                
                                {/* Permission Controls */}
                                <div className="flex items-center gap-1 shrink-0">
                                  <Button
                                    variant={userPermissions[selectedUser.id] === 'access' ? 'default' : 'outline'}
                                    size="sm"
                                    onClick={() => setUserPermissions(prev => ({ ...prev, [selectedUser.id]: 'access' }))}
                                    className="h-7 px-2 text-xs"
                                  >
                                    <Shield className="h-3 w-3 mr-1" />
                                    User
                                  </Button>
                                  <Button
                                    variant={userPermissions[selectedUser.id] === 'admin' ? 'default' : 'outline'}
                                    size="sm"
                                    onClick={() => setUserPermissions(prev => ({ ...prev, [selectedUser.id]: 'admin' }))}
                                    className="h-7 px-2 text-xs"
                                  >
                                    <Crown className="h-3 w-3 mr-1" />
                                    Admin
                                  </Button>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="flex justify-end gap-2">
                      <Button
                        variant="outline"
                        onClick={() => {
                          setShowAddUsers(false);
                          setSelectedUsers([]);
                          setUserPermissions({});
                        }}
                      >
                        Cancel
                      </Button>
                      <Button
                        onClick={handleAddUsers}
                        disabled={Object.keys(userPermissions).length === 0 || submitting}
                      >
                        {submitting && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                        Grant Access
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Remove User Confirmation Dialog */}
      <ConfirmationDialog
        open={showRemoveUserConfirmation}
        onOpenChange={setShowRemoveUserConfirmation}
        onConfirm={confirmRemoveUser}
        title="Remove Template Access"
        description={`Remove ${userToRemove?.name}'s access to the "${graphName}" template?`}
        confirmText="Remove Access"
        variant="default"
      />
    </>
  );
} 