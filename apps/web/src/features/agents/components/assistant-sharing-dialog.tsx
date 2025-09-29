"use client";

import React, { useState, useEffect } from "react";
import { 
  UserPlus, 
  Loader2,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { UserMultiSelect } from "@/components/ui/user-multi-select";
import { toast } from "sonner";
import { useAuthContext } from "@/providers/Auth";
import { Agent } from "@/types/agent";
import { CollaborativeUser } from "@/types/user";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import { UserPermissionsTable } from "@/components/ui/user-permissions-table";
import { PermissionAssignmentTable } from "@/components/ui/permission-assignment-table";
import { Separator } from "@/components/ui/separator";

interface AssistantSharingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  assistant: Agent;
}

interface AssistantPermission {
  user_id: string;
  email: string;
  display_name: string;
  permission_level: 'owner' | 'editor' | 'viewer';
  granted_by: string;
  granted_at: string;
}

interface AssistantPermissionsResponse {
  assistant_id: string;
  assistant_name: string;
  owner_id: string;
  owner_display_name?: string;
  permissions: AssistantPermission[];
  total_users: number;
  shared_users: number;
}

export function AssistantSharingDialog({ open, onOpenChange, assistant }: AssistantSharingDialogProps) {
  const { session } = useAuthContext();
  const [permissions, setPermissions] = useState<AssistantPermission[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAddUsers, setShowAddUsers] = useState(false);
  const [selectedUsers, setSelectedUsers] = useState<CollaborativeUser[]>([]);
  const [userPermissions, setUserPermissions] = useState<Record<string, 'editor' | 'viewer'>>({});
  const [submitting, setSubmitting] = useState(false);
  const [showRemoveUserConfirmation, setShowRemoveUserConfirmation] = useState(false);
  const [userToRemove, setUserToRemove] = useState<{ id: string; name: string } | null>(null);

  const formatUserDisplay = (userId: string, email?: string | null, displayName?: string | null) => {
    // Handle null/undefined values more defensively
    const safeName = displayName && displayName.trim() && displayName !== "Unknown User" ? displayName.trim() : null;
    const safeEmail = email && email.trim() && email !== "Unknown" ? email.trim() : null;
    
    if (safeName) {
      return {
        name: safeName,
        email: safeEmail || userId,
        initials: safeName.slice(0, 2).toUpperCase()
      };
    }
    
    if (safeEmail) {
      return {
        name: safeEmail,
        email: safeEmail,
        initials: safeEmail.slice(0, 2).toUpperCase()
      };
    }
    
    // Fallback to user ID if both display name and email are null/invalid
    return {
      name: userId,
      email: userId,
      initials: userId.slice(0, 2).toUpperCase()
    };
  };

  // Prepare users for the table
  const prepareUsersForTable = () => {
    return permissions.map(permission => {
      const userDisplay = formatUserDisplay(permission.user_id, permission.email, permission.display_name);
      return {
        userId: permission.user_id,
        name: userDisplay.name,
        email: userDisplay.email,
        initials: userDisplay.initials,
        isCurrentUser: permission.user_id === session?.user?.id,
        canRemove: permission.permission_level !== 'owner' || (permission.permission_level === 'owner' && permission.user_id !== session?.user?.id),
        permissionLevel: permission.permission_level,
      };
    });
  };

  const tableUsers = prepareUsersForTable();

  const fetchPermissions = async () => {
    if (!session?.accessToken) {
      toast.error("Authentication required");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`/api/langconnect/agents/assistants/${assistant.assistant_id}/permissions`, {
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) {
        throw new Error("Failed to fetch permissions");
      }

      const data: AssistantPermissionsResponse = await response.json();
      setPermissions(data.permissions);
    } catch (error) {
      console.error("Error fetching permissions:", error);
      toast.error("Failed to load sharing information");
    } finally {
      setLoading(false);
    }
  };

  const handleAddUsers = async () => {
    if (!session?.accessToken) {
      toast.error("Authentication required");
      return;
    }

    const permissionsArray = Object.entries(userPermissions).map(([userId, permissionLevel]) => ({
      user_id: userId,
      permission_level: permissionLevel,
    }));

    if (permissionsArray.length === 0) {
      toast.error("Please select users and permissions");
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch(`/api/langconnect/agents/assistants/${assistant.assistant_id}/share`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.accessToken}`,
        },
        body: JSON.stringify({
          users: permissionsArray,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to share assistant");
      }

      const result = await response.json();
      // Backend returns: { assistant_id, users_shared, notifications_created, successful_shares, failed_shares, errors }
      const createdCount = (result?.notifications_created?.length || 0) + (result?.users_shared?.length || 0);
      const failedCount = result?.failed_shares ?? 0;
      const errorsArr = Array.isArray(result?.errors) ? result.errors : [];

      if (createdCount > 0) {
        toast.success(`Invitations sent to ${createdCount} user${createdCount !== 1 ? 's' : ''}`);
        if (failedCount > 0 || errorsArr.length > 0) {
          const firstError = errorsArr[0] || "Some invitations could not be sent";
          toast.warning(typeof firstError === 'string' ? firstError : JSON.stringify(firstError));
        }
        // Reset state
        setSelectedUsers([]);
        setUserPermissions({});
        setShowAddUsers(false);
        // Refresh permissions
        await fetchPermissions();
      } else if (failedCount > 0 || errorsArr.length > 0) {
        const firstError = errorsArr[0] || "Failed to share assistant";
        throw new Error(typeof firstError === 'string' ? firstError : JSON.stringify(firstError));
      } else {
        toast.info("No changes made");
      }
    } catch (error) {
      console.error("Error sharing assistant:", error);
      toast.error("Failed to add users");
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
      const response = await fetch(`/api/langconnect/agents/assistants/${assistant.assistant_id}/permissions/${userToRemove.id}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to remove user access");
      }

      const result = await response.json();
      
      if (result.revoked) {
        toast.success(`Removed ${userToRemove.name}'s access`);
        await fetchPermissions();
      } else {
        toast.warning(result.message || "No access found to remove");
      }
    } catch (error) {
      console.error("Error removing user access:", error);
      toast.error("Failed to remove user access");
    } finally {
      setUserToRemove(null);
    }
  };

  // Get excluded user IDs (users who already have permissions + current user)
  const excludedUserIds = [
    ...permissions.map(p => p.user_id),
    session?.user?.id || ""
  ].filter(Boolean);

  // Update permissions when selectedUsers change
  useEffect(() => {
    const newPermissions: Record<string, 'editor' | 'viewer'> = {};
    selectedUsers.forEach(user => {
      // Default to viewer if not already set
      newPermissions[user.id] = userPermissions[user.id] || 'viewer';
    });
    setUserPermissions(newPermissions);
  }, [selectedUsers]);

  useEffect(() => {
    if (open) {
      fetchPermissions();
    }
  }, [open]);

  if (!session?.accessToken) {
    return null;
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader className="pb-4">
            <DialogTitle>Manage Agent Access</DialogTitle>
            <DialogDescription>
              Control who has access to the "{assistant.name}" agent and their permission levels.
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

              {loading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin" />
                  <span className="ml-2 text-sm text-muted-foreground">Loading permissions...</span>
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
                    excludeUserIds={excludedUserIds}
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
        title="Remove User Access"
        description={`Remove ${userToRemove?.name}'s access to this agent?`}
        confirmText="Remove Access"
        variant="default"
      />
    </>
  );
} 