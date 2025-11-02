import React, { useCallback, useState } from "react";
import { ToolComponentProps } from "../../types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Download as DownloadIcon, CheckCircle, Loader2, AlertCircle } from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";

interface ProcessOnePagerResult {
  success: boolean;
  filename?: string;
  download_url?: string;
  process_name?: string;
  message?: string;
  error?: string;
}

export function GenerateProcessOnePagerTool({
  toolCall,
  toolResult,
  state,
  streaming
}: ToolComponentProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  // Parse tool result
  let resultData: ProcessOnePagerResult | null = null;
  let errorMessage: string | null = null;

  if (toolResult?.content) {
    try {
      const rawContent = toolResult.content;

      // Handle array content (MessageContentComplex[]) - extract first element
      const content = Array.isArray(rawContent)
        ? (rawContent.length > 0 ? rawContent[0] : null)
        : rawContent;

      if (!content) {
        errorMessage = "No content received from tool";
      } else if (typeof content === "string") {
        // If content is a string, check if it looks like an error message before parsing
        if (content.startsWith("Error:") || content.startsWith("error:")) {
          errorMessage = content;
        } else {
          // Try to parse as JSON
          try {
            const parsed = JSON.parse(content);
            if (parsed.success) {
              resultData = parsed;
            } else {
              errorMessage = parsed.error || parsed.message || "Failed to generate process one-pager";
            }
          } catch {
            // If JSON parsing fails, treat the content as an error message
            errorMessage = content || "Failed to generate process one-pager";
          }
        }
      } else if (typeof content === "object") {
        // Content is already an object
        const parsed = content as unknown as ProcessOnePagerResult;
        if (parsed.success) {
          resultData = parsed;
        } else {
          errorMessage = parsed.error || parsed.message || "Failed to generate process one-pager";
        }
      }
    } catch (e) {
      // Silently handle any unexpected errors in parsing logic
      errorMessage = "An unexpected error occurred while processing the result";
    }
  }

  // Download handler
  const handleDownload = useCallback(async () => {
    if (!resultData?.download_url) return;

    setIsDownloading(true);
    try {
      // Fetch the file from the signed URL
      const response = await fetch(resultData.download_url);

      if (!response.ok) {
        throw new Error(`Download failed: ${response.statusText}`);
      }

      // Get the blob from response
      const blob = await response.blob();

      // Create download link
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = resultData.filename || "process_one_pager.pptx";
      document.body.appendChild(a);
      a.click();

      // Cleanup
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 100);
    } catch (error) {
      console.error('Error downloading process one-pager:', error);
      alert('Failed to download the file. Please try again.');
    } finally {
      setIsDownloading(false);
    }
  }, [resultData]);

  // Loading state
  if (state === "loading" || streaming) {
    return (
      <Card className="w-full p-4">
        <div className="flex items-center gap-3">
          <MinimalistBadge
            icon={Loader2}
            tooltip="Generating process one-pager"
            className="animate-spin-slow"
          />
          <div>
            <h3 className="font-medium text-foreground">
              Generating Process One-Pager...
            </h3>
            <p className="text-sm text-muted-foreground">
              Creating PowerPoint presentation
            </p>
          </div>
        </div>
      </Card>
    );
  }

  // Error state (either from tool execution or parsing)
  if (state === "error" || errorMessage) {
    return (
      <Card className="w-full p-4">
        <div className="flex items-center gap-3">
          <MinimalistBadge
            icon={AlertCircle}
            tooltip="Error generating one-pager"
          />
          <div>
            <h3 className="font-medium text-foreground">
              Error Generating Process One-Pager
            </h3>
            <p className="text-sm text-destructive">
              {errorMessage || "Failed to generate process one-pager"}
            </p>
          </div>
        </div>
      </Card>
    );
  }

  // Success state
  if (resultData) {
    return (
      <Card className="w-full p-4">
        <div className="flex items-center gap-3">
          <MinimalistBadge
            icon={CheckCircle}
            tooltip="Process one-pager generated successfully"
          />
          <div className="flex-1">
            <h3 className="font-medium text-foreground">
              Process One-Pager Generated
            </h3>
            <p className="text-sm text-muted-foreground">
              {resultData.process_name || "Ready to download"}
            </p>
          </div>
          <Button
            onClick={handleDownload}
            variant="default"
            size="sm"
            disabled={isDownloading}
            className="flex items-center gap-2"
          >
            <DownloadIcon className="w-4 h-4" />
            {isDownloading ? "Downloading..." : "Download Process One-Pager"}
          </Button>
        </div>
      </Card>
    );
  }

  // Fallback (should not reach here)
  return null;
}
