"use client";

import type React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { AlertCircle, ChevronDown, Users } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { DESCRIPTION_MAX_LENGTH } from "@/constants";
import { useState } from "react";
import { UserMultiSelect } from "@/components/ui/user-multi-select";
import { UserPermissionSelector } from "@/components/ui/user-permission-selector";
import { CollaborativeUser, ShareAtCreation } from "@/types/user";
import { useAuthContext } from "@/providers/Auth";
import { Badge } from "@/components/ui/badge";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";

interface CreateCollectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger?: React.ReactNode;
  onSubmit: (
    name: string, 
    description: string, 
    shareWith?: ShareAtCreation[]
  ) => Promise<void>;
}

export function CreateCollectionDialog({
  open,
  onOpenChange,
  trigger,
  onSubmit,
}: CreateCollectionDialogProps) {
  const { user } = useAuthContext();
  const [_loading, _setLoading] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [newCollectionDescription, setNewCollectionDescription] = useState("");
  const [sharingExpanded, setSharingExpanded] = useState(false);
  const [selectedUsers, setSelectedUsers] = useState<CollaborativeUser[]>([]);
  const [permissions, setPermissions] = useState<Record<string, 'editor' | 'viewer'>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isDescriptionTooLong =
    newCollectionDescription.length > DESCRIPTION_MAX_LENGTH;

  // Handle user selection changes
  const handleUsersChange = (users: CollaborativeUser[]) => {
    setSelectedUsers(users);
    
    // Initialize permissions for new users (default to viewer)
    const newPermissions = { ...permissions };
    users.forEach(user => {
      if (!(user.id in newPermissions)) {
        newPermissions[user.id] = 'viewer';
      }
    });
    
    // Remove permissions for users no longer selected
    Object.keys(newPermissions).forEach(userId => {
      if (!users.some(user => user.id === userId)) {
        delete newPermissions[userId];
      }
    });
    
    setPermissions(newPermissions);
  };

  // Handle permission changes
  const handlePermissionsChange = (newPermissions: Record<string, 'editor' | 'viewer'>) => {
    setPermissions(newPermissions);
  };

  // Handle user removal from permission selector
  const handleRemoveUser = (userId: string) => {
    setSelectedUsers(selectedUsers.filter(user => user.id !== userId));
    const newPermissions = { ...permissions };
    delete newPermissions[userId];
    setPermissions(newPermissions);
  };

  // Reset form state
  const resetForm = () => {
    setNewCollectionName("");
    setNewCollectionDescription("");
    setSharingExpanded(false);
    setSelectedUsers([]);
    setPermissions({});
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    
    // Prepare sharing data if users are selected
    const shareWith: ShareAtCreation[] | undefined = selectedUsers.length > 0 
      ? selectedUsers.map(user => ({
          user_id: user.id,
          permission_level: permissions[user.id] || 'viewer'
        }))
      : undefined;

    await onSubmit(newCollectionName, newCollectionDescription, shareWith);
    resetForm();
    setIsSubmitting(false);
  };

  // Close handler to reset form
  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      resetForm();
    }
    onOpenChange(isOpen);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
    >
      {trigger && (
        <DialogTrigger asChild>
          {trigger}
        </DialogTrigger>
      )}
      <DialogContent className={cn("max-w-2xl max-h-[90vh]", ...getScrollbarClasses('y'))}>
        <DialogHeader>
          <DialogTitle>Create New Collection</DialogTitle>
          <DialogDescription>
            Enter a name and description for your new collection. Optionally share it with team members.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-6 py-4">
          {/* Basic Collection Info */}
          <div className="space-y-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label
                htmlFor="collection-name"
                className="text-right"
              >
                Name
              </Label>
              <Input
                id="collection-name"
                value={newCollectionName}
                onChange={(e) => setNewCollectionName(e.target.value)}
                className="col-span-3"
                placeholder="Enter collection name..."
              />
            </div>
            
            <div className="grid grid-cols-4 items-start gap-4">
              <Label
                htmlFor="collection-description"
                className="text-right"
              >
                Description
              </Label>
              <div className="col-span-3 space-y-2">
                <Textarea
                  id="collection-description"
                  value={newCollectionDescription}
                  onChange={(e) => setNewCollectionDescription(e.target.value)}
                  placeholder="Describe what this collection will contain..."
                />
                <div className="text-muted-foreground text-right text-xs">
                  {newCollectionDescription.length}/{DESCRIPTION_MAX_LENGTH}{" "}
                  characters
                </div>
              </div>
            </div>
            
            {isDescriptionTooLong && (
              <div className="mt-2">
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    Description exceeds the maximum length of{" "}
                    {DESCRIPTION_MAX_LENGTH} characters.
                  </AlertDescription>
                </Alert>
              </div>
            )}
          </div>

          <Separator />

          {/* Sharing Section */}
          <Collapsible 
            open={sharingExpanded} 
            onOpenChange={setSharingExpanded}
          >
            <CollapsibleTrigger asChild>
              <Button 
                variant="ghost" 
                className="flex w-full items-center justify-between p-0 hover:bg-transparent"
              >
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4" />
                  <span className="text-sm font-medium">
                    Share with team members
                  </span>
                  {selectedUsers.length > 0 && (
                    <Badge variant="secondary" className="ml-2">
                      {selectedUsers.length} user{selectedUsers.length === 1 ? '' : 's'}
                    </Badge>
                  )}
                </div>
                <ChevronDown className={`h-4 w-4 transition-transform ${sharingExpanded ? 'rotate-180' : ''}`} />
              </Button>
            </CollapsibleTrigger>
            
            <CollapsibleContent className="space-y-4 pt-4">
              <div className="text-sm text-muted-foreground">
                Add team members who should have access to this collection. You will automatically be the owner.
              </div>
              
              <UserMultiSelect
                selectedUsers={selectedUsers}
                onUsersChange={handleUsersChange}
                excludeUserIds={user?.id ? [user.id] : []}
                maxUsers={10}
                placeholder="Search for team members to share with..."
              />
              
              {selectedUsers.length > 0 && (
                <UserPermissionSelector
                  users={selectedUsers}
                  permissions={permissions}
                  onPermissionsChange={handlePermissionsChange}
                  onRemoveUser={handleRemoveUser}
                  showBulkActions={selectedUsers.length > 1}
                />
              )}
            </CollapsibleContent>
          </Collapsible>
        </div>
        
        <DialogFooter className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            {selectedUsers.length > 0 ? (
              <span>Will share with {selectedUsers.length} team member{selectedUsers.length === 1 ? '' : 's'}</span>
            ) : (
              <span>Collection will be private to you</span>
            )}
          </div>
          
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={
                !newCollectionName.trim() || isDescriptionTooLong || isSubmitting
              }
            >
              {isSubmitting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                selectedUsers.length > 0 ? "Create & Share" : "Create"
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
