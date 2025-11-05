import React, { useMemo } from "react";
import { ToolMessage } from "@langchain/langgraph-sdk";
import { MarkdownText } from "@/components/ui/markdown-text";
import { extractImagesFromResponse } from "@/lib/image-utils";
import { ImageGrid } from "./ImageGrid";

interface ToolResultDisplayProps {
  toolResult: ToolMessage;
}

function isComplexValue(value: any): boolean {
  return Array.isArray(value) || (typeof value === "object" && value !== null);
}

export function ToolResultDisplay({ toolResult }: ToolResultDisplayProps) {

  let parsedContent: any;
  let isJsonContent = false;

  try {
    if (typeof toolResult.content === "string") {
      parsedContent = JSON.parse(toolResult.content);
      isJsonContent = isComplexValue(parsedContent);
    } else if (typeof toolResult.content === "object") {
      parsedContent = toolResult.content;
      isJsonContent = true;
    }
  } catch {
    // Content is not JSON, use as is
    parsedContent = toolResult.content;
  }

  const contentStr = isJsonContent
    ? JSON.stringify(parsedContent, null, 2)
    : String(toolResult.content);

  // Extract images from the tool result content
  const extractedImages = useMemo(() => {
    return extractImagesFromResponse(toolResult.content);
  }, [toolResult.content]);

  const hasImages = extractedImages.length > 0;

  return (
    <div className="space-y-3">
      {/* Images Section - rendered first if any images are detected */}
      {hasImages && (
        <div className="space-y-1.5">
          <div className="text-xs uppercase tracking-wide text-muted-foreground font-medium">
            Images
          </div>
          <ImageGrid images={extractedImages} />
        </div>
      )}

      {/* Original Content Section */}
      <div className="space-y-1.5">
        {hasImages && (
          <div className="text-xs uppercase tracking-wide text-muted-foreground font-medium">
            Result
          </div>
        )}
        <div className="rounded-md bg-muted/40 p-2.5">
          {isJsonContent ? (
            <table className="min-w-full text-sm table-fixed">
              <tbody>
                {(Array.isArray(parsedContent)
                  ? parsedContent
                  : Object.entries(parsedContent)
                ).map((item, idx) => {
                  const [key, value] = Array.isArray(parsedContent)
                    ? [idx, item]
                    : [item[0], item[1]];
                  return (
                    <tr key={idx}>
                      <td className="pr-4 py-1 text-muted-foreground font-medium w-1/4 break-anywhere align-top">
                        {String(key)}
                      </td>
                      <td className="py-1 font-mono w-3/4 break-anywhere min-w-0">
                        {isComplexValue(value) ? (
                          <code className="text-xs break-anywhere">
                            {JSON.stringify(value, null, 2)}
                          </code>
                        ) : (
                          <span className="break-anywhere">{String(value)}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="font-mono text-sm break-preserve min-w-0">
              <MarkdownText>{contentStr}</MarkdownText>
            </div>
          )}
        </div>
      </div>
    </div>
  );
} 