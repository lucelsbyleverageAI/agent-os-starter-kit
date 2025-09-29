"use client";

import { useState, useEffect } from "react";
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
import { Memory } from "@/types/memory";
import { useMemoriesContext } from "../providers/Memories";

interface EditMemoryDialogProps {
  memory: Memory | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditMemoryDialog({ memory, open, onOpenChange }: EditMemoryDialogProps) {
  const { updateMemory } = useMemoriesContext();
  const [content, setContent] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (memory && open) {
      setContent(memory.memory);
    }
  }, [memory, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!memory || !content.trim()) {
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await updateMemory(memory.id, content.trim(), memory.metadata);
      if (result) {
        onOpenChange(false);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    if (memory) {
      setContent(memory.memory);
    }
    onOpenChange(false);
  };

  if (!memory) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>Edit Memory</DialogTitle>
          <DialogDescription>
            Update the content of this memory. Changes will be saved and available for AI agents.
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
              {isSubmitting ? "Saving..." : "Save Changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
