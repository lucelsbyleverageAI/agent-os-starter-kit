import React from "react";
import { Label } from "@/components/ui/label";
import { MarkdownText } from "@/components/ui/markdown-text";
import { prettifyText } from "@/features/chat/utils/interrupt-utils";

interface ToolArgumentsTableProps {
  args: Record<string, any>;
}

export function ToolArgumentsTable({ args }: ToolArgumentsTableProps) {
  if (!args || Object.keys(args).length === 0) {
    return (
      <div className="rounded-md bg-muted/40 p-2.5 text-sm text-muted-foreground">
        No arguments
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-2.5">
      {Object.entries(args).map(([key, value]) => {
        let displayValue = "";
        if (["string", "number"].includes(typeof value)) {
          displayValue = value.toString();
        } else {
          displayValue = JSON.stringify(value, null, 2);
        }

        return (
          <div key={`args-${key}`} className="grid grid-cols-[160px_1fr] items-start gap-x-3 gap-y-1">
            <Label className="text-xs text-muted-foreground mt-1 truncate">
              {prettifyText(key)}
            </Label>
            <div className="rounded-md bg-muted/40 p-2.5 font-mono text-[13px] leading-relaxed break-anywhere min-w-0">
              <MarkdownText>{displayValue}</MarkdownText>
            </div>
          </div>
        );
      })}
    </div>
  );
} 