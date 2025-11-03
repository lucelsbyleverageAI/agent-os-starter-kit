"use client";

import React, { useState, useEffect } from "react";
import { Loader2, AlertTriangle } from "lucide-react";
import { type ExtractedImage } from "@/lib/image-utils";
import { ImagePreviewDialog } from "@/components/ui/image-preview-dialog";

interface ImageGridProps {
  images: ExtractedImage[];
}

/**
 * ImageGrid component that displays a grid of extracted images
 * with preview functionality
 */
export function ImageGrid({ images }: ImageGridProps) {
  if (images.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">
        {images.length} {images.length === 1 ? 'image' : 'images'} generated
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {images.map((image, index) => (
          <ImageCard key={index} image={image} index={index} />
        ))}
      </div>
    </div>
  );
}

/**
 * Individual image card with preview modal
 */
function ImageCard({ image, index }: { image: ExtractedImage; index: number }) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewImage, setPreviewImage] = useState<{url: string, title: string} | null>(null);
  const [displayName, setDisplayName] = useState(`Image ${index + 1}`);
  const [imageSize, setImageSize] = useState<string | null>(null);

  // Load image URL based on type
  useEffect(() => {
    const loadImage = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const { getImageRenderUrl } = await import('@/lib/image-utils');
        const url = await getImageRenderUrl(image);
        setImageUrl(url);
      } catch (err) {
        console.error('Failed to load image:', err);
        setError(err instanceof Error ? err.message : 'Failed to load image');
      } finally {
        setIsLoading(false);
      }
    };

    loadImage();
  }, [image]);

  // Load display name and size
  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const { getImageDisplayName, getImageSize } = await import('@/lib/image-utils');
        setDisplayName(getImageDisplayName(image));
        const size = getImageSize(image);
        setImageSize(size);
      } catch (err) {
        console.error('Failed to load image metadata:', err);
        // Keep default values
      }
    };

    loadMetadata();
  }, [image, index]);

  if (isLoading) {
    return (
      <div className="aspect-square bg-muted rounded-lg flex items-center justify-center border border-border">
        <div className="text-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mx-auto mb-2" />
          <p className="text-xs text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (error || !imageUrl) {
    return (
      <div className="aspect-square bg-destructive/10 border border-destructive/20 rounded-lg flex items-center justify-center">
        <div className="text-center p-3">
          <AlertTriangle className="h-5 w-5 text-destructive mx-auto mb-2" />
          <p className="text-xs text-destructive break-words">
            {error || 'Failed to load'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="bg-card border border-border rounded-lg overflow-hidden hover:shadow-md transition-shadow">
        <div
          className="aspect-square bg-muted cursor-pointer relative group overflow-hidden"
          onClick={() => setPreviewImage({ url: imageUrl, title: displayName })}
        >
          <img
            src={imageUrl}
            alt={displayName}
            className="w-full h-full object-contain bg-background"
            style={{ display: 'block' }}
            onError={() => {
              console.error('Image failed to load:', imageUrl);
              setError('Failed to display image');
            }}
          />
          {/* Hover overlay */}
          <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center">
            <div className="opacity-0 group-hover:opacity-100 transition-opacity text-white text-xs bg-black/50 px-2 py-1 rounded">
              Click to preview
            </div>
          </div>
        </div>

        <div className="p-2.5">
          <div className="flex items-center justify-between gap-2">
            <h4 className="font-medium text-xs text-foreground truncate flex-1">
              {displayName}
            </h4>
            <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded uppercase flex-shrink-0">
              {image.type}
            </span>
          </div>

          {imageSize && (
            <p className="text-[10px] text-muted-foreground mt-1">{imageSize}</p>
          )}
        </div>
      </div>

      {/* Image Preview Modal - same as used in user messages */}
      {previewImage && (
        <ImagePreviewDialog
          open={!!previewImage}
          onOpenChange={(open) => !open && setPreviewImage(null)}
          imageUrl={previewImage.url}
          title={previewImage.title}
        />
      )}
    </>
  );
}
