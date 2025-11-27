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
  ExternalLink
} from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { cn } from "@/lib/utils";

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
function getFileIcon(mimeType: string) {
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
    } catch (e) {
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
      // Build download URL
      const params = new URLSearchParams({
        storage_path: fileData.storage_path,
        bucket: 'agent-outputs',
      });

      const response = await fetch(`/api/langconnect/storage/thread-file?${params.toString()}`);

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
    <Card className="w-full overflow-hidden">
      <div className="p-4">
        <div className="flex items-start gap-4">
          {/* File Icon */}
          <div className={cn(
            "w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0",
            "bg-primary/10"
          )}>
            <FileIcon className="w-6 h-6 text-primary" />
          </div>

          {/* File Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-medium text-foreground truncate">
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
            </div>

            {fileData.description && (
              <p className="text-sm text-muted-foreground mb-2 line-clamp-2">
                {fileData.description}
              </p>
            )}

            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span>{fileData.filename}</span>
              {fileData.file_size > 0 && (
                <>
                  <span className="text-border">|</span>
                  <span>{formatFileSize(fileData.file_size)}</span>
                </>
              )}
            </div>
          </div>

          {/* Download Button */}
          <Button
            onClick={handleDownload}
            disabled={isDownloading || !fileData.storage_path}
            variant="default"
            size="sm"
            className="flex-shrink-0"
          >
            {isDownloading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Downloading...
              </>
            ) : (
              <>
                <DownloadIcon className="w-4 h-4 mr-2" />
                Download
              </>
            )}
          </Button>
        </div>
      </div>
    </Card>
  );
}
