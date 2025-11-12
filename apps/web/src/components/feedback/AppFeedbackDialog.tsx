"use client";

import { useState, useRef } from "react";
import { toast } from "sonner";
import { X, Upload } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getSupabaseClient } from "@/lib/auth/supabase-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

interface AppFeedbackDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type FeedbackType = "bug" | "feature";

interface UploadedImage {
  storage_path: string;
  preview_url: string;
  filename: string;
}

export function AppFeedbackDialog({ open, onOpenChange }: AppFeedbackDialogProps) {
  const [feedbackType, setFeedbackType] = useState<FeedbackType>("bug");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    // Check maximum images limit (5)
    if (uploadedImages.length + files.length > 5) {
      toast.error("You can upload a maximum of 5 screenshots");
      return;
    }

    setIsUploading(true);

    try {
      // Get authentication token
      const supabase = getSupabaseClient();
      const { data: { session }, error: sessionError } = await supabase.auth.getSession();

      if (sessionError || !session?.access_token) {
        toast.error("Authentication required. Please sign in.");
        return;
      }

      // Upload each file
      const uploadPromises = Array.from(files).map(async (file) => {
        // Validate file type
        const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff'];
        if (!allowedTypes.includes(file.type)) {
          toast.error(`Invalid file type: ${file.name}. Only images are allowed.`);
          return null;
        }

        // Validate file size (50MB limit)
        const maxSize = 50 * 1024 * 1024;
        if (file.size > maxSize) {
          toast.error(`File ${file.name} exceeds 50MB limit`);
          return null;
        }

        // Upload to backend
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/api/langconnect/storage/upload-support-image', {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || `Failed to upload ${file.name}`);
        }

        const data = await response.json();
        return {
          storage_path: data.storage_path,
          preview_url: data.preview_url,
          filename: data.filename,
        };
      });

      const results = await Promise.all(uploadPromises);
      const successfulUploads = results.filter((result): result is UploadedImage => result !== null);

      if (successfulUploads.length > 0) {
        setUploadedImages((prev) => [...prev, ...successfulUploads]);
        toast.success(`Uploaded ${successfulUploads.length} screenshot(s)`);
      }
    } catch (error) {
      console.error('Failed to upload screenshots:', error);
      toast.error(error instanceof Error ? error.message : 'Failed to upload screenshots');
    } finally {
      setIsUploading(false);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleRemoveImage = (index: number) => {
    setUploadedImages((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async () => {
    // Validation
    if (!title.trim()) {
      toast.error("Please enter a title");
      return;
    }

    if (!description.trim()) {
      toast.error("Please enter a description");
      return;
    }

    setIsSubmitting(true);

    try {
      // Get authentication token
      const supabase = getSupabaseClient();
      const { data: { session }, error: sessionError } = await supabase.auth.getSession();

      if (sessionError || !session?.access_token) {
        toast.error("Authentication required. Please sign in.");
        return;
      }

      // Auto-capture context
      const pageUrl = window.location.href;
      const userAgent = navigator.userAgent;
      const metadata = {
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight,
        },
        screen: {
          width: window.screen.width,
          height: window.screen.height,
        },
        timestamp: new Date().toISOString(),
      };

      const response = await fetch("/api/langconnect/feedback/app", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          feedback_type: feedbackType,
          title: title.trim(),
          description: description.trim(),
          screenshot_urls: uploadedImages.map((img) => img.storage_path),
          page_url: pageUrl,
          user_agent: userAgent,
          metadata,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to submit feedback");
      }

      toast.success("Feedback submitted successfully! Thank you for helping us improve.");

      // Reset form and close
      setTitle("");
      setDescription("");
      setFeedbackType("bug");
      setUploadedImages([]);
      onOpenChange(false);
    } catch (error) {
      console.error("Failed to submit feedback:", error);
      toast.error(error instanceof Error ? error.message : "Failed to submit feedback. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen && !isSubmitting) {
      // Reset form when closing
      setTitle("");
      setDescription("");
      setFeedbackType("bug");
      setUploadedImages([]);
    }
    onOpenChange(newOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[550px]">
        <DialogHeader>
          <DialogTitle>Submit Feedback</DialogTitle>
          <DialogDescription>
            Help us improve by reporting bugs or suggesting new features.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-4">
          {/* Feedback Type */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Feedback Type</Label>
            <RadioGroup
              value={feedbackType}
              onValueChange={(value) => setFeedbackType(value as FeedbackType)}
            >
              <div className="space-y-2">
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="bug" id="bug" />
                  <Label htmlFor="bug" className="font-normal cursor-pointer">
                    <span className="font-medium">Bug Report</span> - Something
                    isn&apos;t working correctly
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="feature" id="feature" />
                  <Label htmlFor="feature" className="font-normal cursor-pointer">
                    <span className="font-medium">Feature Request</span> - Suggest a
                    new feature or improvement
                  </Label>
                </div>
              </div>
            </RadioGroup>
          </div>

          {/* Title */}
          <div className="space-y-2">
            <Label htmlFor="title" className="text-sm font-medium">
              Title <span className="text-destructive">*</span>
            </Label>
            <Input
              id="title"
              placeholder={
                feedbackType === "bug"
                  ? "Brief description of the issue"
                  : "Brief description of your idea"
              }
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={255}
              disabled={isSubmitting}
            />
            <p className="text-xs text-muted-foreground">
              {title.length}/255 characters
            </p>
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="description" className="text-sm font-medium">
              Description <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="description"
              placeholder={
                feedbackType === "bug"
                  ? "What happened? What did you expect to happen? Steps to reproduce..."
                  : "Describe your feature idea and how it would help..."
              }
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={6}
              className="resize-none"
              disabled={isSubmitting}
            />
          </div>

          {/* Screenshots */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">
              Screenshots <span className="text-muted-foreground font-normal">(Optional)</span>
            </Label>

            {/* Upload Button */}
            <div className="flex flex-col gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={isSubmitting || isUploading || uploadedImages.length >= 5}
                className="w-full"
              >
                <Upload className="h-4 w-4 mr-2" />
                {isUploading ? "Uploading..." : "Upload Screenshots"}
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp,image/bmp,image/tiff"
                multiple
                onChange={handleImageUpload}
                className="hidden"
              />

              {/* Image Previews */}
              {uploadedImages.length > 0 && (
                <div className="grid grid-cols-2 gap-2">
                  {uploadedImages.map((image, index) => (
                    <div
                      key={index}
                      className="relative group rounded-md border overflow-hidden bg-muted"
                    >
                      <img
                        src={image.preview_url}
                        alt={image.filename}
                        className="w-full h-32 object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => handleRemoveImage(index)}
                        disabled={isSubmitting}
                        className="absolute top-1 right-1 p-1 bg-destructive text-destructive-foreground rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                        aria-label="Remove image"
                      >
                        <X className="h-3 w-3" />
                      </button>
                      <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-xs p-1 truncate">
                        {image.filename}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <p className="text-xs text-muted-foreground">
                {uploadedImages.length > 0
                  ? `${uploadedImages.length}/5 screenshots uploaded`
                  : "Add up to 5 screenshots to help illustrate the issue or feature"}
              </p>
            </div>
          </div>

          {/* Context Info */}
          <div className="text-xs text-muted-foreground border-t pt-3">
            <p className="font-medium mb-1">Automatically captured:</p>
            <ul className="list-disc list-inside space-y-0.5 ml-1">
              <li>Current page URL</li>
              <li>Browser information</li>
              <li>Screen resolution</li>
            </ul>
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="ghost"
            onClick={() => handleOpenChange(false)}
            disabled={isSubmitting}
            type="button"
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting} type="button">
            {isSubmitting ? "Submitting..." : "Submit Feedback"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
