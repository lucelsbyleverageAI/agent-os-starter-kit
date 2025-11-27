import React from "react";
import { File, X as XIcon, FileText, ZoomIn } from "lucide-react";
import type { Base64ContentBlock } from "@langchain/core/messages";
import { cn } from "@/lib/utils";
import Image from "next/image";

export interface MultimodalPreviewProps {
  block: Base64ContentBlock;
  removable?: boolean;
  onRemove?: () => void;
  className?: string;
  size?: "sm" | "md" | "lg";
  expandable?: boolean;
  onExpand?: (imageUrl: string, imageTitle: string) => void;
}

export const MultimodalPreview: React.FC<MultimodalPreviewProps> = ({
  block,
  removable = false,
  onRemove,
  className,
  size = "md",
  expandable = false,
  onExpand,
}) => {
  // Hidden XML blocks for backend processing - don't render in UI
  // These are used for sandbox file transfer metadata
  if ((block as any).metadata?.is_hidden_xml) {
    return null;
  }

  // Image block with base64 data (legacy)
  if (
    block.type === "image" &&
    block.source_type === "base64" &&
    typeof block.mime_type === "string" &&
    block.mime_type.startsWith("image/")
  ) {
    const url = `data:${block.mime_type};base64,${block.data}`;
    const imageTitle = String(block.metadata?.name || "uploaded image");
    let imgClass: string = "rounded-xl object-cover h-16 w-16 text-lg";
    if (size === "sm") imgClass = "rounded-xl object-cover h-10 w-10 text-base";
    if (size === "lg") imgClass = "rounded-xl object-cover h-24 w-24 text-xl";

    const imageElement = (
      <Image
        src={url}
        alt={imageTitle}
        className={imgClass}
        width={size === "sm" ? 16 : size === "md" ? 32 : 48}
        height={size === "sm" ? 16 : size === "md" ? 32 : 48}
      />
    );

    return (
      <div className={cn("relative inline-block group", className)}>
        {expandable && onExpand ? (
          <button
            type="button"
            className="relative rounded-xl overflow-hidden transition-all hover:ring-2 hover:ring-primary focus:outline-none focus:ring-2 focus:ring-primary"
            onClick={(e) => {
              e.stopPropagation();
              onExpand(url, imageTitle);
            }}
            aria-label="Expand image"
          >
            {imageElement}
            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <ZoomIn className="h-6 w-6 text-white" />
            </div>
          </button>
        ) : (
          imageElement
        )}
        {removable && (
          <button
            type="button"
            className="absolute -top-1 -right-1 z-10 rounded-full bg-background border border-border text-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            onClick={onRemove}
            aria-label="Remove image"
          >
            <XIcon className="h-4 w-4" />
          </button>
        )}
      </div>
    );
  }

  // Image block with storage path (new approach)
  if (
    block.type === "image" &&
    (block as any).source_type === "url" &&
    typeof (block as any).url === "string"
  ) {
    // Use the storage path to generate a fresh signed URL on-demand via proxy route
    // This solves the expiry problem where preview_url expires after 30 minutes
    const storagePath = String(block.metadata?.storage_path || (block as any).url || '');
    const bucket = String(block.metadata?.bucket || 'chat-uploads');
    const displayUrl = `/api/langconnect/storage/image?path=${encodeURIComponent(storagePath)}&bucket=${encodeURIComponent(bucket)}`;
    const imageTitle = String(block.metadata?.name || "uploaded image");
    let imgClass: string = "rounded-xl object-cover h-16 w-16 text-lg";
    if (size === "sm") imgClass = "rounded-xl object-cover h-10 w-10 text-base";
    if (size === "lg") imgClass = "rounded-xl object-cover h-24 w-24 text-xl";

    const imageElement = (
      <Image
        src={displayUrl}
        alt={imageTitle}
        className={imgClass}
        width={size === "sm" ? 16 : size === "md" ? 32 : 48}
        height={size === "sm" ? 16 : size === "md" ? 32 : 48}
        unoptimized  // Required for external URLs from storage
      />
    );

    return (
      <div className={cn("relative inline-block group", className)}>
        {expandable && onExpand ? (
          <button
            type="button"
            className="relative rounded-xl overflow-hidden transition-all hover:ring-2 hover:ring-primary focus:outline-none focus:ring-2 focus:ring-primary"
            onClick={(e) => {
              e.stopPropagation();
              onExpand(displayUrl, imageTitle);
            }}
            aria-label="Expand image"
          >
            {imageElement}
            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <ZoomIn className="h-6 w-6 text-white" />
            </div>
          </button>
        ) : (
          imageElement
        )}
        {removable && (
          <button
            type="button"
            className="absolute -top-1 -right-1 z-10 rounded-full bg-background border border-border text-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            onClick={onRemove}
            aria-label="Remove image"
          >
            <XIcon className="h-4 w-4" />
          </button>
        )}
      </div>
    );
  }

  // File block (PDF, document, or extracted text)
  if (
    block.type === "file" &&
    block.source_type === "base64"
  ) {
    const filename =
      block.metadata?.filename || block.metadata?.name || "Document";
    const isExtractedText = block.metadata?.extracted_text;
    
    return (
      <div
        className={cn(
          "relative flex items-start gap-2 rounded-xl border border-border bg-muted px-3 py-2",
          className,
        )}
      >
        <div className="flex flex-shrink-0 flex-col items-start justify-start">
          {isExtractedText ? (
            <FileText
              className={cn(
                "flex-shrink-0 text-muted-foreground",
                size === "sm" ? "h-5 w-5" : "h-7 w-7",
              )}
            />
          ) : (
            <File
              className={cn(
                "flex-shrink-0 text-muted-foreground",
                size === "sm" ? "h-5 w-5" : "h-7 w-7",
              )}
            />
          )}
        </div>
        <span
          className={cn("min-w-0 flex-1 text-sm break-all text-foreground")}
          style={{ wordBreak: "break-all", whiteSpace: "pre-wrap" }}
        >
          {String(filename)}
        </span>
        {removable && (
          <button
            type="button"
            className="ml-2 self-start rounded-full bg-background border border-border p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            onClick={onRemove}
            aria-label="Remove file"
          >
            <XIcon className="h-4 w-4" />
          </button>
        )}
      </div>
    );
  }

  // Text block with extracted document content
  if (
    (block as any).type === "text" &&
    (block as any).metadata?.extracted_text
  ) {
    const filename = (block as any).metadata?.filename || "Document";
    
    return (
      <div
        className={cn(
          "relative flex items-start gap-2 rounded-xl border border-border bg-muted px-3 py-2",
          className,
        )}
      >
        <div className="flex flex-shrink-0 flex-col items-start justify-start">
          <FileText
            className={cn(
              "flex-shrink-0 text-muted-foreground",
              size === "sm" ? "h-5 w-5" : "h-7 w-7",
            )}
          />
        </div>
        <span
          className={cn("min-w-0 flex-1 text-sm break-all text-foreground")}
          style={{ wordBreak: "break-all", whiteSpace: "pre-wrap" }}
        >
          {String(filename)}
        </span>
        {removable && (
          <button
            type="button"
            className="ml-2 self-start rounded-full bg-background border border-border p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            onClick={onRemove}
            aria-label="Remove file"
          >
            <XIcon className="h-4 w-4" />
          </button>
        )}
      </div>
    );
  }

  // Fallback for unknown types
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-xl border border-border bg-muted px-3 py-2 text-muted-foreground",
        className,
      )}
    >
      <File className="h-5 w-5 flex-shrink-0" />
      <span className="truncate text-xs">Unsupported file type</span>
      {removable && (
        <button
          type="button"
          className="ml-2 rounded-full bg-background border border-border p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          onClick={onRemove}
          aria-label="Remove file"
        >
          <XIcon className="h-4 w-4" />
        </button>
      )}
    </div>
  );
};
