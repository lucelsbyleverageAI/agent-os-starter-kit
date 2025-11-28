import React, { useState, useCallback } from "react";
import { ToolComponentProps } from "../../types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Download as DownloadIcon,
  FileText,
  FileSpreadsheet,
  FileImage,
  File,
  CheckCircle,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { cn } from "@/lib/utils";
import { useFilePreviewOptional } from "@/features/chat/context/file-preview-context";

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

// Helper to get appropriate icon for file type
function getFileIcon(mimeType: string | undefined) {
  if (!mimeType) {
    return File;
  }
  if (mimeType.startsWith('image/')) {
    return FileImage;
  }
  if (mimeType.includes('spreadsheet') || mimeType.includes('excel') || mimeType === 'text/csv') {
    return FileSpreadsheet;
  }
  if (mimeType.includes('document') || mimeType.includes('word') || mimeType === 'application/pdf') {
    return FileText;
  }
  return File;
}

// Helper to format file size
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// Helper to get file extension badge color
function getFileTypeBadgeClass(fileType: string): string {
  const ext = fileType.toLowerCase().replace('.', '');
  switch (ext) {
    case 'pdf':
      return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300';
    case 'docx':
    case 'doc':
      return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300';
    case 'xlsx':
    case 'xls':
    case 'csv':
      return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300';
    case 'pptx':
    case 'ppt':
      return 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300';
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'webp':
      return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300';
    default:
      return 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
  }
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

  const FileIcon = fileData ? getFileIcon(fileData.mime_type) : File;

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
            <div className={cn(
              "w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0",
              "bg-primary/10"
            )}>
              <FileIcon className="w-5 h-5 text-primary" />
            </div>

            {/* File Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium text-foreground truncate">
                  {fileData.display_name}
                </h3>
                {fileData.file_type && (
                  <span className={cn(
                    "text-xs font-medium px-2 py-0.5 rounded-full uppercase",
                    getFileTypeBadgeClass(fileData.file_type)
                  )}>
                    {fileData.file_type.replace('.', '')}
                  </span>
                )}
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
