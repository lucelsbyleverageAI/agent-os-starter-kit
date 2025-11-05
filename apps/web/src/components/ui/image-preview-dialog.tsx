"use client";

import React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";

export interface ImagePreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  imageUrl: string;
  title: string;
}

/**
 * Dialog for previewing images in full size
 *
 * Usage:
 * ```tsx
 * <ImagePreviewDialog
 *   open={showPreview}
 *   onOpenChange={setShowPreview}
 *   imageUrl="https://..."
 *   title="My Image"
 * />
 * ```
 */
export function ImagePreviewDialog({
  open,
  onOpenChange,
  imageUrl,
  title,
}: ImagePreviewDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-7xl max-h-[95vh] p-0">
        <DialogHeader className="px-6 pt-6 pb-3">
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <div
          className={cn(
            "relative w-full flex items-center justify-center bg-muted/30 px-6 pb-6",
            ...getScrollbarClasses('both')
          )}
        >
          {imageUrl ? (
            <img
              src={imageUrl}
              alt={title}
              className="max-w-full max-h-[75vh] object-contain rounded-lg"
              onError={(e) => {
                // Fallback for failed image loads
                const target = e.target as HTMLImageElement;
                target.src = '/placeholder-image.svg';
                target.alt = 'Failed to load image';
              }}
            />
          ) : (
            <div className="flex items-center justify-center h-64 text-muted-foreground">
              No image available
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
