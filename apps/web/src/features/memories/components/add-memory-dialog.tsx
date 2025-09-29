"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useMemoriesContext } from "../providers/Memories";

interface AddMemoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddMemoryDialog({ open, onOpenChange }: AddMemoryDialogProps) {
  const { addMemory } = useMemoriesContext();
  const [content, setContent] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!content.trim()) {
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await addMemory(content.trim());
      if (result) {
        setContent("");
        onOpenChange(false);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    setContent("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>Add New Memory</DialogTitle>
          <DialogDescription>
            Create a new memory that will be stored and can be retrieved by AI agents during conversations.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="memory-content">Memory Content</Label>
            <Textarea
              id="memory-content"
              placeholder="Enter the memory content..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={4}
              className="min-h-[100px]"
              disabled={isSubmitting}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={handleCancel}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!content.trim() || isSubmitting}
            >
              {isSubmitting ? "Adding..." : "Add Memory"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
