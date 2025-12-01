"use client";

import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { UserPlus, Loader2 } from 'lucide-react';
import type { Skill, SkillPermission } from '@/types/skill';
import { CollaborativeUser } from '@/types/user';
import { UserMultiSelect } from '@/components/ui/user-multi-select';
import { useAuthContext } from "@/providers/Auth";
import { useUsers } from "@/hooks/use-users";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { UserPermissionsTable } from "@/components/ui/user-permissions-table";
import { PermissionAssignmentTable } from "@/components/ui/permission-assignment-table";
import { Separator } from "@/components/ui/separator";

interface ManageSkillAccessDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  skill: Skill;
}

export function ManageSkillAccessDialog({ open, onOpenChange, skill }: ManageSkillAccessDialogProps) {
  const { user, session } = useAuthContext();
  const { getUsersByIds } = useUsers();
  const [permissions, setPermissions] = useState<SkillPermission[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAddUsers, setShowAddUsers] = useState(false);
  const [selectedUsers, setSelectedUsers] = useState<CollaborativeUser[]>([]);
  const [userPermissions, setUserPermissions] = useState<Record<string, 'editor' | 'viewer'>>({});
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
      } catch (error) {
        console.error('Failed to load user details:', error);
      } finally {
        setUserDetailsLoading(false);
      }
    };

    if (!loading) {
      loadUserDetails();
    }
  }, [permissions, getUsersByIds, loading]);

  // Helper function to format user display
  const formatUserDisplay = (userId: string) => {
    const userDetail = userDetailsMap[userId];
    if (!userDetail) return {
      name: userId,
      email: userId,
      initials: userId.slice(0, 2).toUpperCase()
    };

    const safeName = userDetail.display_name && userDetail.display_name.trim() ? userDetail.display_name.trim() : null;
    const safeEmail = userDetail.email && userDetail.email.trim() ? userDetail.email.trim() : null;
    const safeFirstName = userDetail.first_name && userDetail.first_name.trim() ? userDetail.first_name.trim() : null;
    const safeLastName = userDetail.last_name && userDetail.last_name.trim() ? userDetail.last_name.trim() : null;

    if (safeName) {
      return {
        name: safeName,
        email: safeEmail || userId,
        initials: safeName.slice(0, 2).toUpperCase()
      };
    }

    if (safeFirstName && safeLastName) {
      const fullName = `${safeFirstName} ${safeLastName}`;
      return {
        name: fullName,
        email: safeEmail || userId,
        initials: `${safeFirstName[0]}${safeLastName[0]}`.toUpperCase()
      };
    }

    if (safeEmail) {
      return {
        name: safeEmail,
        email: safeEmail,
        initials: safeEmail.slice(0, 2).toUpperCase()
      };
    }

    return {
      name: userId,
      email: userId,
      initials: userId.slice(0, 2).toUpperCase()
    };
  };

  // Prepare users for the table
  const prepareUsersForTable = () => {
    return permissions.map(permission => {
      const userDisplay = formatUserDisplay(permission.user_id);
      return {
        userId: permission.user_id,
        name: typeof userDisplay === 'string' ? userDisplay : userDisplay.name,
        email: typeof userDisplay === 'string' ? userDisplay : userDisplay.email,
        initials: typeof userDisplay === 'string'
          ? permission.user_id.slice(0, 2).toUpperCase()
          : userDisplay.initials,
        isCurrentUser: permission.user_id === user?.id,
        canRemove: permission.permission_level !== 'owner',
        permissionLevel: permission.permission_level,
      };
    });
  };

  const tableUsers = prepareUsersForTable();

  // Fetch skill permissions when dialog opens
  useEffect(() => {
    if (open && skill.id) {
      fetchPermissions();
    }
  }, [open, skill.id]);

  const fetchPermissions = async () => {
    if (!session?.accessToken) {
      toast.error('Authentication required');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`/api/langconnect/skills/${skill.id}/permissions`, {
        headers: {
          'Authorization': `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch permissions');
      }

      const data = await response.json();
      setPermissions(data);
    } catch (error) {
      console.error('Error fetching permissions:', error);
      toast.error('Failed to load access information');
    } finally {
      setLoading(false);
    }
  };

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
      const response = await fetch(`/api/langconnect/skills/${skill.id}/share`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.accessToken}`,
        },
        body: JSON.stringify({
          users: permissionsArray,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to share skill');
      }

      toast.success('Users added successfully');

      // Reset state
      setSelectedUsers([]);
      setUserPermissions({});
      setShowAddUsers(false);

      // Refresh permissions
      await fetchPermissions();
    } catch (error) {
      console.error('Error sharing skill:', error);
      toast.error('Failed to add users');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemoveUser = async (userId: string, userName?: string) => {
    setUserToRemove({ id: userId, name: userName || 'User' });
    setShowRemoveUserConfirmation(true);
  };

  const confirmRemoveUser = async () => {
    if (!userToRemove || !session?.accessToken) {
      toast.error('Authentication required');
      return;
    }

    try {
      const response = await fetch(`/api/langconnect/skills/${skill.id}/permissions/${userToRemove.id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${session.accessToken}`,
        },
      });

      if (response.ok) {
        toast.success(`Removed ${userToRemove.name}'s access`);

        // Refresh permissions immediately
        try {
          await fetchPermissions();
        } catch (fetchError) {
          console.error('Error refreshing permissions after successful delete:', fetchError);
        }
        return;
      }

      // Handle error cases
      const errorText = await response.text();
      console.error('Delete API error:', errorText);

      // If we get a 500 error, check if the deletion actually worked
      if (response.status === 500) {
        try {
          await fetchPermissions();
          const userStillExists = permissions.some(p => p.user_id === userToRemove.id);
          if (!userStillExists) {
            toast.success(`Removed ${userToRemove.name}'s access`);
            return;
          }
        } catch (fetchError) {
          console.error('Error checking permissions after 500:', fetchError);
        }
      }

      throw new Error(`Failed to remove user: ${response.status} - ${errorText}`);
    } catch (error) {
      console.error('Error removing user:', error);
      toast.error('Failed to remove user access');
    } finally {
      setUserToRemove(null);
    }
  };

  // Smart exclude logic: exclude current user AND users who already have access
  const excludeUserIds = [
    ...(user?.id ? [user.id] : []),
    ...permissions.map(p => p.user_id)
  ];

  // Update permissions when selectedUsers change
  useEffect(() => {
    const newPermissions: Record<string, 'editor' | 'viewer'> = {};
    selectedUsers.forEach(user => {
      newPermissions[user.id] = userPermissions[user.id] || 'viewer';
    });
    setUserPermissions(newPermissions);
  }, [selectedUsers]);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader className="pb-4">
            <DialogTitle>Manage Skill Access</DialogTitle>
            <DialogDescription>
              Control who has access to &quot;{skill.name}&quot; and their permission levels.
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
                  users={tableUsers}
                  onRemoveUser={handleRemoveUser}
                  className="border rounded-lg p-2"
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

                  <PermissionAssignmentTable
                    selectedUsers={selectedUsers}
                    userPermissions={userPermissions}
                    onPermissionChange={(userId, permission) =>
                      setUserPermissions(prev => ({ ...prev, [userId]: permission }))
                    }
                    onRemoveUser={(userId) =>
                      setSelectedUsers(prev => prev.filter(user => user.id !== userId))
                    }
                  />

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
        title="Remove Skill Access"
        description={`Remove ${userToRemove?.name}'s access to the "${skill.name}" skill?`}
        confirmText="Remove Access"
        variant="destructive"
      />
    </>
  );
}
