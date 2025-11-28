import React, { useState, useCallback, useEffect, useRef } from "react";
import { ToolComponentProps } from "../../types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Download as DownloadIcon,
  CheckCircle,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { useFilePreviewOptional } from "@/features/chat/context/file-preview-context";
import { formatFileSize } from "@/lib/file-utils";
import { BrandedFileIcon } from "@/components/ui/branded-file-icon";

interface PublishedFileData {
  display_name: string;
  description: string;
  filename: string;
  file_type: string;
  mime_type: string;
  file_size: number;
  storage_path: string;
  sandbox_path: string;
  published_at: string;
}

export function PublishFileTool({
  toolCall,
  toolResult,
  state,
  streaming,
  onRetry
}: ToolComponentProps) {
  const [isDownloading, setIsDownloading] = useState(false);
  const filePreview = useFilePreviewOptional();

  // Parse tool result
  let fileData: PublishedFileData | null = null;
  if (state === "completed" && toolResult?.content) {
    try {
      const content = typeof toolResult.content === "string"
        ? toolResult.content
        : JSON.stringify(toolResult.content);

      // The tool returns a JSON string with the file data
      const parsed = JSON.parse(content);
      fileData = parsed;
    } catch {
      // Tool might return a simple message, try to extract from args
      try {
        fileData = {
          display_name: toolCall.args?.display_name || 'Published File',
          description: toolCall.args?.description || '',
          filename: toolCall.args?.file_path?.split('/').pop() || 'file',
          file_type: '',
          mime_type: 'application/octet-stream',
          file_size: 0,
          storage_path: '',
          sandbox_path: toolCall.args?.file_path || '',
          published_at: new Date().toISOString(),
        };
      } catch {
        fileData = null;
      }
    }
  }

  // Handle download
  const handleDownload = useCallback(async () => {
    if (!fileData?.storage_path) return;

    setIsDownloading(true);
    try {
      // Build download URL using on-demand signed URL endpoint
      const params = new URLSearchParams({
        path: fileData.storage_path,
        bucket: 'agent-outputs',
        filename: fileData.filename,
      });

      const response = await fetch(`/api/langconnect/storage/download?${params.toString()}`);

      if (!response.ok) {
        throw new Error('Download failed');
      }

      // Get blob and trigger download
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileData.filename;
      document.body.appendChild(a);
      a.click();

      // Cleanup
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 100);
    } catch (error) {
      console.error('Download error:', error);
    } finally {
      setIsDownloading(false);
    }
  }, [fileData]);

  // Handler to open preview - must be before any conditional returns (Rules of Hooks)
  const handleOpenPreview = useCallback(() => {
    if (fileData && filePreview) {
      filePreview.openPreview({
        display_name: fileData.display_name,
        filename: fileData.filename,
        file_type: fileData.file_type,
        mime_type: fileData.mime_type,
        storage_path: fileData.storage_path,
        file_size: fileData.file_size,
        description: fileData.description,
      });
    }
  }, [fileData, filePreview]);

  // Track if we observed a loading/streaming state (meaning tool ran during this session)
  const wasLoadingRef = useRef(false);
  // Track if we've already auto-opened the preview for this tool call
  const hasAutoOpenedRef = useRef(false);

  // Track if we ever saw a loading state
  useEffect(() => {
    if (state === "loading" || streaming) {
      wasLoadingRef.current = true;
    }
  }, [state, streaming]);

  // Auto-open preview when tool completes successfully (only if we saw loading first)
  useEffect(() => {
    if (state === "completed" && fileData && filePreview &&
        !hasAutoOpenedRef.current && wasLoadingRef.current) {
      hasAutoOpenedRef.current = true;
      handleOpenPreview();
    }
  }, [state, fileData, filePreview, handleOpenPreview]);

  // Loading state
  if (state === "loading" || streaming) {
    return (
      <Card className="w-full p-4">
        <div className="flex items-center gap-3">
          <MinimalistBadge
            icon={Loader2}
            tooltip="Publishing file"
            className="animate-spin-slow"
          />
          <div>
            <h3 className="font-medium text-foreground">
              Publishing file...
            </h3>
            <p className="text-sm text-muted-foreground">
              Uploading to storage
            </p>
          </div>
        </div>
      </Card>
    );
  }

  // Error state
  if (state === "error") {
    return (
      <Card className="w-full p-4">
        <div className="flex items-center gap-3 mb-3">
          <MinimalistBadge
            icon={AlertCircle}
            tooltip="Error publishing file"
          />
          <div>
            <h3 className="font-medium text-foreground">
              Error Publishing File
            </h3>
            <p className="text-sm text-muted-foreground">
              Failed to publish file for download
            </p>
          </div>
        </div>
        {onRetry && (
          <Button onClick={onRetry} variant="outline" size="sm">
            Retry
          </Button>
        )}
      </Card>
    );
  }

  // No file data
  if (!fileData) {
    return (
      <Card className="w-full p-4">
        <div className="flex items-center gap-3">
          <MinimalistBadge
            icon={CheckCircle}
            tooltip="File published"
          />
          <div>
            <h3 className="font-medium text-foreground">
              File Published
            </h3>
            <p className="text-sm text-muted-foreground">
              {toolCall.args?.display_name || 'File available for download'}
            </p>
          </div>
        </div>
      </Card>
    );
  }

  // Success state with file card
  return (
    <Card
      className="w-full overflow-hidden py-0 gap-0 cursor-pointer hover:bg-accent/50 transition-colors"
      onClick={handleOpenPreview}
    >
        <div className="py-5 px-3">
          <div className="flex items-center gap-3">
            {/* File Icon */}
            <BrandedFileIcon extension={fileData.file_type} size={24} className="flex-shrink-0" />

            {/* File Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium text-foreground truncate">
                  {fileData.display_name}
                </h3>
                {fileData.file_size > 0 && (
                  <span className="text-xs text-muted-foreground">
                    ({formatFileSize(fileData.file_size)})
                  </span>
                )}
              </div>

              {fileData.description && (
                <p className="text-xs text-muted-foreground line-clamp-1">
                  {fileData.description}
                </p>
              )}
            </div>

            {/* Download Button */}
            <Button
              onClick={(e) => {
                e.stopPropagation(); // Prevent card click
                handleDownload();
              }}
              disabled={isDownloading || !fileData.storage_path}
              variant="default"
              size="sm"
              className="flex-shrink-0 h-8 text-xs"
            >
              {isDownloading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  Downloading...
                </>
              ) : (
                <>
                  <DownloadIcon className="w-3.5 h-3.5 mr-1.5" />
                  Download
                </>
              )}
            </Button>
          </div>
        </div>
    </Card>
  );
}
