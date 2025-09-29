import React from "react";
import type { Base64ContentBlock } from "@langchain/core/messages";
import { MultimodalPreview } from "./MultimodalPreview";
import { cn } from "@/lib/utils";
import { ProcessingAttachment, MAX_TOTAL_ATTACHMENTS_SIZE } from "@/hooks/use-file-upload";
import { Loader2 } from "lucide-react";
import { X } from "lucide-react";

interface ContentBlocksPreviewProps {
  blocks: Base64ContentBlock[];
  processingAttachments?: ProcessingAttachment[];
  onRemove: (idx: number) => void;
  onRemoveProcessing?: (id: string) => void;
  size?: "sm" | "md" | "lg";
  className?: string;
  showSizeIndicator?: boolean;
  calculateTotalSize?: () => number;
  formatFileSize?: (bytes: number) => string;
}

/**
 * Renders a preview of content blocks with optional remove functionality.
 * Uses cn utility for robust class merging.
 */
export const ContentBlocksPreview: React.FC<ContentBlocksPreviewProps> = ({
  blocks,
  processingAttachments = [],
  onRemove,
  onRemoveProcessing,
  size = "md",
  className,
  showSizeIndicator = false,
  calculateTotalSize,
  formatFileSize,
}) => {
  if (!blocks.length && !processingAttachments.length) return null;

  // Calculate size usage if functions are provided
  const totalSize = showSizeIndicator && calculateTotalSize ? calculateTotalSize() : 0;
  const sizePercentage = totalSize > 0 ? (totalSize / MAX_TOTAL_ATTACHMENTS_SIZE) * 100 : 0;
  const isNearLimit = sizePercentage > 80;

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {/* Size indicator */}
      {showSizeIndicator && totalSize > 0 && formatFileSize && (
        <div className="px-3.5 pt-3.5 pb-0">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Attachment size:</span>
            <span className={cn(
              isNearLimit ? "text-orange-600 font-medium" : "text-muted-foreground"
            )}>
              {formatFileSize(totalSize)} / {formatFileSize(MAX_TOTAL_ATTACHMENTS_SIZE)}
            </span>
          </div>
          <div className="mt-1 h-1 bg-muted rounded-full overflow-hidden">
            <div 
              className={cn(
                "h-full transition-all duration-300",
                isNearLimit ? "bg-orange-500" : "bg-primary"
              )}
              style={{ width: `${Math.min(sizePercentage, 100)}%` }}
            />
          </div>
        </div>
      )}
      
      <div className="flex flex-wrap gap-2 p-3.5 pb-0">
        {/* Render regular content blocks */}
        {blocks.map((block, idx) => (
        <MultimodalPreview
          key={idx}
          block={block}
          removable
          onRemove={() => onRemove(idx)}
          size={size}
        />
      ))}

      {/* Render processing attachments */}
      {processingAttachments.map((attachment) => (
        <div
          key={attachment.id}
          className={cn(
            "relative flex items-start gap-2 rounded-xl border border-border bg-muted px-3 py-2",
            attachment.status === "error" && "border-destructive bg-destructive/10"
          )}
        >
          <div className="flex flex-shrink-0 flex-col items-start justify-start">
            {attachment.status === "processing" ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : attachment.status === "error" ? (
              <span className="text-destructive">!</span>
            ) : null}
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm text-foreground break-all">
              {attachment.file.name}
            </span>
            {attachment.status === "processing" && (
              <span className="text-xs text-muted-foreground">Processing...</span>
            )}
            {attachment.status === "error" && (
              <span className="text-xs text-destructive">{attachment.error}</span>
            )}
          </div>
          {onRemoveProcessing && (
            <button
              type="button"
              className="ml-2 self-start rounded-full bg-background border border-border p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
              onClick={() => onRemoveProcessing(attachment.id)}
              aria-label="Remove processing attachment"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      ))}
      </div>
    </div>
  );
};
