"use client";

import React, { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { useAuthContext } from "@/providers/Auth";

interface EditDocumentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string | null;
  collectionId: string;
  currentTitle: string;
  currentDescription: string;
  onSuccess: () => void | Promise<void>;
}

export function EditDocumentDialog({
  open,
  onOpenChange,
  documentId,
  collectionId,
  currentTitle,
  currentDescription,
  onSuccess,
}: EditDocumentDialogProps) {
  const { session } = useAuthContext();
  const [title, setTitle] = useState(currentTitle);
  const [description, setDescription] = useState(currentDescription);
  const [submitting, setSubmitting] = useState(false);

  // Update form when props change
  useEffect(() => {
    setTitle(currentTitle);
    setDescription(currentDescription);
  }, [currentTitle, currentDescription, open]);

  const handleSubmit = async () => {
    if (!documentId || !session?.accessToken) return;

    // Validate title is not empty
    if (!title.trim()) {
      toast.error("Title is required", {
        richColors: true,
        description: "Please enter a title for the document"
      });
      return;
    }

    setSubmitting(true);

    try {
      // Call API to update document metadata
      const formData = new FormData();
      formData.append("title", title.trim());
      formData.append("description", description.trim());

      const response = await fetch(`/api/langconnect/collections/${collectionId}/documents/${documentId}`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${session.accessToken}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to update document");
      }

      toast.success("Document updated successfully", {
        richColors: true,
        description: "Title and description have been updated"
      });

      onOpenChange(false);
      if (onSuccess) {
        await onSuccess();
      }
    } catch (error) {
      console.error("Failed to update document:", error);
      toast.error("Failed to update document", {
        richColors: true,
        description: error instanceof Error ? error.message : "An error occurred"
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    if (submitting) return;
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className={cn("!max-w-2xl flex flex-col gap-0", ...getScrollbarClasses('y'))}>
        <DialogHeader className="pb-4">
          <DialogTitle>Edit Title & Description</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Title Field */}
          <div className="space-y-2">
            <Label htmlFor="document-title" className="text-sm font-medium">
              Title <span className="text-destructive">*</span>
            </Label>
            <Input
              id="document-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Enter document title"
              disabled={submitting}
              className="focus-visible:ring-0 focus-visible:ring-offset-0"
            />
          </div>

          {/* Description Field */}
          <div className="space-y-2">
            <Label htmlFor="document-description" className="text-sm font-medium">
              Description
            </Label>
            <Textarea
              id="document-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add a description to help with semantic search (optional)"
              rows={4}
              disabled={submitting}
              className={cn("resize-none focus-visible:ring-0 focus-visible:ring-offset-0", ...getScrollbarClasses('y'))}
            />
            <p className="text-xs text-muted-foreground">
              A good description helps agents find and understand this document better
            </p>
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between pt-6 mt-2 border-t">
          <Button variant="outline" onClick={handleClose} disabled={submitting}>
            Cancel
          </Button>
          <Button 
            onClick={handleSubmit} 
            disabled={submitting || !title.trim()}
          >
            {submitting ? (
              <div className="flex items-center space-x-2">
                <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Saving...</span>
              </div>
            ) : (
              "Save Changes"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

