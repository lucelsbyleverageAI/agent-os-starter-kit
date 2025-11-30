import { useCallback, useLayoutEffect, useState, useEffect } from "react";
import { useQueryState } from "nuqs";
import { TooltipIconButton } from "@/components/ui/tooltip-icon-button";
import { SquarePen } from "lucide-react";
import { useFilePreviewOptional } from "@/features/chat/context/file-preview-context";

interface NewThreadButtonProps {
  hasMessages: boolean;
}

export function NewThreadButton({ hasMessages }: NewThreadButtonProps) {
  const [_, setThreadId] = useQueryState("threadId");
  const [isMac, setIsMac] = useState<boolean | null>(null);
  const filePreview = useFilePreviewOptional();

  const handleNewThread = useCallback(() => {
    filePreview?.closePreview();
    setThreadId(null);
  }, [setThreadId, filePreview]);

  // Detect OS only on client side to avoid hydration mismatch
  useEffect(() => {
    setIsMac(/(Mac|iPhone|iPod|iPad)/i.test(navigator.userAgent));
  }, []);

  useLayoutEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        (e.metaKey || e.ctrlKey) &&
        e.shiftKey &&
        e.key.toLocaleLowerCase() === "o"
      ) {
        e.preventDefault();
        handleNewThread();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleNewThread]);

  // Only show the new thread button if there are messages
  if (!hasMessages) {
    return null;
  }

  // Use generic tooltip until client has hydrated to avoid mismatch
  const tooltipText = isMac === null 
    ? "New thread" 
    : isMac 
      ? "New thread (Cmd+Shift+O)" 
      : "New thread (Ctrl+Shift+O)";

  return (
    <TooltipIconButton
      size="sm"
      className="size-8 text-muted-foreground hover:bg-accent"
      tooltip={tooltipText}
      variant="ghost"
      onClick={handleNewThread}
    >
      <SquarePen className="size-4" />
    </TooltipIconButton>
  );
} 