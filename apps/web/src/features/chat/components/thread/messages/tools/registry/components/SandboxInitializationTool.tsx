import { ToolComponentProps } from "../../types";
import { Loader2 } from "lucide-react";

/**
 * Tool component for sandbox initialization status.
 *
 * This component displays a loading indicator while the skills_deepagent
 * sandbox is being initialized (creating sandbox, loading skills, etc.).
 *
 * Behavior:
 * - Loading state: Shows spinner with friendly message
 * - Completed state: Returns null (component disappears)
 * - Error state: Returns null (let default error handling take over)
 *
 * The component is designed to be unobtrusive - it simply provides
 * visual feedback during the potentially lengthy initialization process.
 */
export function SandboxInitializationTool({ state }: ToolComponentProps) {
  // When completed or error, render nothing (disappear completely)
  if (state === "completed" || state === "error") {
    return null;
  }

  // Loading state - show spinner with message
  return (
    <div className="flex items-center gap-3 py-3 px-4 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>Setting up the agent environment, hang tight...</span>
    </div>
  );
}
