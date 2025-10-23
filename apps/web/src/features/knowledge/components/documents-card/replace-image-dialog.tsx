"use client";

import React, { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Upload, Loader2, X, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";
import { replaceDocumentImage } from "@/lib/image-utils";
import { cn } from "@/lib/utils";

export interface ReplaceImageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string;
  collectionId: string;
  currentImageUrl: string;
  currentTitle: string;
  accessToken: string;
  onSuccess?: () => void | Promise<void>;
}

/**
 * Dialog for replacing an image document's file
 *
 * Allows user to upload a new image file which will replace the existing one.
 * The new image will be analyzed by AI vision and the document will be updated.
 */
export function ReplaceImageDialog({
  open,
  onOpenChange,
  documentId,
  collectionId,
  currentImageUrl,
  currentTitle,
  accessToken,
  onSuccess,
}: ReplaceImageDialogProps) {
  const [newImageFile, setNewImageFile] = useState<File | null>(null);
  const [newImagePreview, setNewImagePreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  // Handle file drop
  const onDrop = useCallback((acceptedFiles: File[]) => {
    const file = acceptedFiles[0];
    if (!file) return;

    setNewImageFile(file);

    // Create preview URL
    const previewUrl = URL.createObjectURL(file);
    setNewImagePreview(previewUrl);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/png': ['.png'],
      'image/gif': ['.gif'],
      'image/webp': ['.webp'],
      'image/bmp': ['.bmp'],
      'image/tiff': ['.tiff', '.tif'],
    },
    multiple: false,
    maxSize: 50 * 1024 * 1024, // 50MB
  });

  // Clear selection
  const handleClearSelection = () => {
    setNewImageFile(null);
    if (newImagePreview) {
      URL.revokeObjectURL(newImagePreview);
      setNewImagePreview(null);
    }
  };

  // Handle upload
  const handleUpload = async () => {
    if (!newImageFile) {
      toast.error("No file selected", {
        richColors: true,
        description: "Please select an image file to upload",
      });
      return;
    }

    setUploading(true);

    const loadingToast = toast.loading("Replacing image", {
      richColors: true,
      description: "Uploading new image and running AI analysis...",
    });

    try {
      const result = await replaceDocumentImage(
        collectionId,
        documentId,
        newImageFile,
        accessToken
      );

      toast.dismiss(loadingToast);
      toast.success("Image replaced successfully", {
        richColors: true,
        description: `AI detected: "${result.metadata.title}"`,
      });

      // Clean up
      handleClearSelection();
      onOpenChange(false);

      // Call success callback
      if (onSuccess) {
        await onSuccess();
      }
    } catch (error) {
      toast.dismiss(loadingToast);
      console.error("Failed to replace image:", error);
      toast.error("Failed to replace image", {
        richColors: true,
        description: error instanceof Error ? error.message : "An error occurred",
      });
    } finally {
      setUploading(false);
    }
  };

  // Clean up preview URL on unmount
  React.useEffect(() => {
    return () => {
      if (newImagePreview) {
        URL.revokeObjectURL(newImagePreview);
      }
    };
  }, [newImagePreview]);

  // Reset state when dialog closes
  React.useEffect(() => {
    if (!open) {
      handleClearSelection();
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Replace Image</DialogTitle>
          <DialogDescription>
            Upload a new image to replace "{currentTitle}". The new image will be analyzed by AI
            to extract metadata and descriptions.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Current Image */}
          <div>
            <h3 className="text-sm font-medium mb-2">Current Image</h3>
            <div className="relative w-full max-h-48 overflow-hidden rounded-lg border bg-muted">
              {currentImageUrl ? (
                <img
                  src={currentImageUrl}
                  alt={currentTitle}
                  className="w-full h-auto object-contain max-h-48"
                />
              ) : (
                <div className="flex items-center justify-center h-48 text-muted-foreground">
                  <ImageIcon className="h-12 w-12" />
                </div>
              )}
            </div>
          </div>

          {/* New Image Selection */}
          <div>
            <h3 className="text-sm font-medium mb-2">New Image</h3>

            {!newImageFile ? (
              // Dropzone
              <div
                {...getRootProps()}
                className={cn(
                  "relative border-2 border-dashed rounded-lg p-8 transition-colors cursor-pointer",
                  "hover:border-primary hover:bg-accent/50",
                  isDragActive && "border-primary bg-accent/50"
                )}
              >
                <input {...getInputProps()} />
                <div className="flex flex-col items-center justify-center gap-2 text-center">
                  <Upload className={cn(
                    "h-10 w-10 transition-colors",
                    isDragActive ? "text-primary" : "text-muted-foreground"
                  )} />
                  <div>
                    <p className="text-sm font-medium">
                      {isDragActive ? "Drop image here" : "Drop image or click to upload"}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Supports JPG, PNG, GIF, WebP (max 50MB)
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              // Preview
              <div className="space-y-3">
                <div className="relative w-full rounded-lg border bg-muted overflow-hidden">
                  <img
                    src={newImagePreview || ''}
                    alt="New image preview"
                    className="w-full h-auto object-contain max-h-64"
                  />
                  <Button
                    variant="destructive"
                    size="icon"
                    className="absolute top-2 right-2 h-8 w-8"
                    onClick={handleClearSelection}
                    disabled={uploading}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <ImageIcon className="h-4 w-4 text-muted-foreground" />
                  <span className="font-medium truncate">{newImageFile.name}</span>
                  <span className="text-muted-foreground">
                    ({(newImageFile.size / 1024 / 1024).toFixed(2)} MB)
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={uploading}
          >
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!newImageFile || uploading}
          >
            {uploading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                Replace Image
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
