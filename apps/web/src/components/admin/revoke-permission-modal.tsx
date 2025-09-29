"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { PublicGraphPermission, PublicAssistantPermission, PublicCollectionPermission } from "@/types/public-permissions";

type Permission = PublicGraphPermission | PublicAssistantPermission | PublicCollectionPermission;
type RevokeMode = 'revoke_all' | 'future_only';
type ActionType = 'revoke' | 're_invoke' | 'revoke_all';

interface RevokePermissionModalProps {
  item: Permission | null;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (mode: RevokeMode) => void;
  isLoading: boolean;
  actionType?: ActionType;
}

export const RevokePermissionModal = ({ 
  item, 
  isOpen, 
  onClose, 
  onConfirm, 
  isLoading, 
  actionType = 'revoke' 
}: RevokePermissionModalProps) => {
  const [revokeMode, setRevokeMode] = useState<RevokeMode>('revoke_all');

  if (!item) return null;

  const getItemName = () => {
    if ('graph_id' in item) {
      return item.graph_display_name || item.graph_id;
    } else if ('assistant_id' in item) {
      return item.assistant_display_name || item.assistant_id;
    } else {
      return item.collection_display_name || item.collection_id;
    }
  };

  const itemName = getItemName();

  const handleConfirm = () => {
    if (actionType === 're_invoke') {
      // For re-invoke, we don't need a mode - just re-enable the permission
      onConfirm('future_only'); // This will be handled differently in the backend
    } else if (actionType === 'revoke_all') {
      // Force revoke all mode
      onConfirm('revoke_all');
    } else {
      // Normal revoke with user choice
      onConfirm(revokeMode);
    }
  };

  const getModalContent = () => {
    if (actionType === 're_invoke') {
      return {
        title: `Re-invoke Public Access for "${itemName}"?`,
        description: 'This will restore public access for future users. Existing users who already have access will keep it.',
        showRadioGroup: false,
        confirmText: 'Re-invoke Access',
        confirmVariant: 'default' as const
      };
    } else if (actionType === 'revoke_all') {
      return {
        title: `Revoke All Access for "${itemName}"?`,
        description: 'This will immediately remove access for all users who received it automatically. This action cannot be undone.',
        showRadioGroup: false,
        confirmText: 'Revoke All Access',
        confirmVariant: 'destructive' as const
      };
    } else {
      return {
        title: `Revoke Public Access for "${itemName}"?`,
        description: 'Choose how you want to revoke this public permission. This action cannot be undone.',
        showRadioGroup: true,
        confirmText: 'Confirm Revocation',
        confirmVariant: 'destructive' as const
      };
    }
  };

  const modalContent = getModalContent();

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{modalContent.title}</DialogTitle>
          <DialogDescription>
            {modalContent.description}
          </DialogDescription>
        </DialogHeader>

        {modalContent.showRadioGroup && (
          <div className="py-4">
            <RadioGroup value={revokeMode} onValueChange={(value: RevokeMode) => setRevokeMode(value)}>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="revoke_all" id="r1" />
                <Label htmlFor="r1" className="font-medium">Revoke for Everyone</Label>
              </div>
              <p className="text-sm text-muted-foreground pl-6">
                Immediately remove access for all users who received it automatically.
              </p>

              <div className="flex items-center space-x-2 pt-4">
                <RadioGroupItem value="future_only" id="r2" />
                <Label htmlFor="r2" className="font-medium">Future Users Only</Label>
              </div>
              <p className="text-sm text-muted-foreground pl-6">
                Prevent new users from gaining access. Existing users will keep their access.
              </p>
            </RadioGroup>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button variant={modalContent.confirmVariant} onClick={handleConfirm} disabled={isLoading}>
            {isLoading ? "Processing..." : modalContent.confirmText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}; 