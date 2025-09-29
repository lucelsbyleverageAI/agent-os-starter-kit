"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface ConfirmationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  isLoading?: boolean;
  variant?: "default" | "destructive";
}

export function ConfirmationDialog({
  open,
  onOpenChange,
  onConfirm,
  title,
  description,
  confirmText = "Confirm",
  cancelText = "Cancel",
  isLoading = false,
  variant = "default",
}: ConfirmationDialogProps) {
  const confirmButtonClass = variant === "destructive" 
    ? "bg-destructive hover:bg-destructive/90 text-white"
    : "";

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>{cancelText}</AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={isLoading}
            className={confirmButtonClass}
          >
            {isLoading ? "Processing..." : confirmText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// Backwards compatibility wrapper for existing thread delete usage
export function ThreadDeleteDialog({
  open,
  onOpenChange,
  onConfirm,
  isLoading = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  isLoading?: boolean;
}) {
  return (
    <ConfirmationDialog
      open={open}
      onOpenChange={onOpenChange}
      onConfirm={onConfirm}
      title="Delete Thread"
      description="Are you sure you want to delete this thread? This action cannot be undone."
      confirmText="Delete"
      isLoading={isLoading}
      variant="destructive"
    />
  );
}

// New dialog for warning about large messages
export function LargeMessageWarningDialog({
  open,
  onOpenChange,
  onConfirm,
  characterCount,
  isLoading = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  characterCount: number;
  isLoading?: boolean;
}) {
  const formatNumber = (num: number) => num.toLocaleString();

  return (
    <ConfirmationDialog
      open={open}
      onOpenChange={onOpenChange}
      onConfirm={onConfirm}
      title="Large Message Warning"
      description={`This message contains ${formatNumber(characterCount)} characters and may be expensive to process. Large messages can result in higher processing costs. Are you sure you want to proceed?`}
      confirmText="Send Anyway"
      cancelText="Cancel"
      isLoading={isLoading}
      variant="default"
    />
  );
} 