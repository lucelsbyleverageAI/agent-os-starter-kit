import React, { useEffect, useState } from "react";
import { useAgentVersions } from "@/hooks/use-agent-versions";
import { AssistantVersion } from "@/types/agent";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ChevronDown, ChevronRight, RefreshCw, Tag } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { getTagLabel } from "@/lib/agent-tags";

interface VersionsTabProps {
  assistantId: string;
  permissionLevel?: "owner" | "editor" | "viewer" | "admin";
  onVersionRestored?: () => void;
}

export function VersionsTab({
  assistantId,
  permissionLevel = "viewer",
  onVersionRestored,
}: VersionsTabProps) {
  const { versions, loading, error, fetchVersions, restoreVersion } =
    useAgentVersions(assistantId);

  const [expandedVersion, setExpandedVersion] = useState<number | null>(null);
  const [restoreDialogOpen, setRestoreDialogOpen] = useState(false);
  const [restoreTargetVersion, setRestoreTargetVersion] =
    useState<AssistantVersion | null>(null);
  const [restoreCommitMessage, setRestoreCommitMessage] = useState("");

  // Fetch versions on mount
  useEffect(() => {
    fetchVersions();
  }, [fetchVersions]);

  const handleRestoreClick = (version: AssistantVersion) => {
    setRestoreTargetVersion(version);
    setRestoreCommitMessage(`Restored from version ${version.version}`);
    setRestoreDialogOpen(true);
  };

  const handleRestoreConfirm = async () => {
    if (!restoreTargetVersion) return;

    const success = await restoreVersion(
      restoreTargetVersion.version,
      restoreCommitMessage || undefined
    );

    if (success) {
      setRestoreDialogOpen(false);
      setRestoreTargetVersion(null);
      setRestoreCommitMessage("");
      onVersionRestored?.();
    }
  };

  const canRestore = permissionLevel === "owner" || permissionLevel === "editor" || permissionLevel === "admin";

  if (loading) {
    return (
      <div className="space-y-4 p-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center">
        <p className="text-sm text-destructive mb-4">{error}</p>
        <Button onClick={fetchVersions} variant="outline" size="sm">
          <RefreshCw className="mr-2 h-4 w-4" />
          Try Again
        </Button>
      </div>
    );
  }

  if (versions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center">
        <p className="text-sm text-muted-foreground">
          No version history available yet.
        </p>
        <p className="text-xs text-muted-foreground mt-2">
          Versions will appear here after you make changes to this agent.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h3 className="text-sm font-medium">Version History</h3>
          <p className="text-xs text-muted-foreground">
            {versions.length} version{versions.length !== 1 ? "s" : ""} total
          </p>
        </div>
        <Button onClick={fetchVersions} variant="ghost" size="sm">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      <div className={cn("space-y-2 max-h-[500px] overflow-y-auto pr-2", getScrollbarClasses())}>
        {versions.map((version) => (
          <VersionItem
            key={version.version}
            version={version}
            isExpanded={expandedVersion === version.version}
            onToggleExpand={() =>
              setExpandedVersion(
                expandedVersion === version.version ? null : version.version
              )
            }
            onRestore={() => handleRestoreClick(version)}
            canRestore={canRestore && !version.is_latest}
          />
        ))}
      </div>

      {/* Restore confirmation dialog - using Dialog instead of AlertDialog to avoid nesting issues */}
      <Dialog open={restoreDialogOpen} onOpenChange={setRestoreDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Restore to version {restoreTargetVersion?.version}?</DialogTitle>
            <DialogDescription>
              This will create a new version with the configuration from
              version {restoreTargetVersion?.version}.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-4">
            <Label htmlFor="restore-commit-message">
              Commit Message <span className="text-xs text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="restore-commit-message"
              value={restoreCommitMessage}
              onChange={(e) => setRestoreCommitMessage(e.target.value)}
              placeholder="Describe why you're restoring this version..."
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRestoreDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleRestoreConfirm}>
              Restore Version
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface VersionItemProps {
  version: AssistantVersion;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onRestore: () => void;
  canRestore: boolean;
}

function VersionItem({
  version,
  isExpanded,
  onToggleExpand,
  onRestore,
  canRestore,
}: VersionItemProps) {
  const formattedDate = React.useMemo(() => {
    try {
      return formatDistanceToNow(new Date(version.created_at), {
        addSuffix: true,
      });
    } catch {
      return "Unknown date";
    }
  }, [version.created_at]);

  return (
    <div className="border rounded-lg p-3 hover:bg-accent/50 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Badge variant={version.is_latest ? "default" : "outline"} className="text-xs">
              v{version.version}
            </Badge>
            {version.is_latest && (
              <Badge variant="secondary" className="text-xs">
                Latest
              </Badge>
            )}
          </div>

          <p className="text-xs text-muted-foreground mb-1">{formattedDate}</p>

          {version.commit_message && (
            <p className="text-sm text-foreground mb-2">
              {version.commit_message}
            </p>
          )}

          {version.created_by_display_name && (
            <p className="text-xs text-muted-foreground">
              by {version.created_by_display_name}
            </p>
          )}

          {/* Tags display */}
          {version.tags && version.tags.length > 0 && (
            <div className="flex items-center gap-1 mt-2 flex-wrap">
              <Tag className="h-3 w-3 text-muted-foreground" />
              {version.tags.map((tag) => (
                <Badge key={tag} variant="outline" className="text-xs py-0">
                  {getTagLabel(tag)}
                </Badge>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {canRestore && (
            <Button
              type="button"
              onClick={onRestore}
              variant="outline"
              size="sm"
              className="text-xs"
            >
              Restore
            </Button>
          )}
        </div>
      </div>

      {/* Collapsible config preview */}
      <Collapsible open={isExpanded} onOpenChange={onToggleExpand}>
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="w-full mt-2 text-xs justify-start"
          >
            {isExpanded ? (
              <ChevronDown className="mr-1 h-3 w-3" />
            ) : (
              <ChevronRight className="mr-1 h-3 w-3" />
            )}
            {isExpanded ? "Hide" : "Show"} Configuration
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-2 p-3 bg-muted rounded-md space-y-3">
            {/* Version metadata summary */}
            <div className="text-xs space-y-1">
              <p><span className="font-medium">Name:</span> {version.name}</p>
              {version.description && (
                <p><span className="font-medium">Description:</span> {version.description}</p>
              )}
              {version.tags && version.tags.length > 0 && (
                <p><span className="font-medium">Tags:</span> {version.tags.map(t => getTagLabel(t)).join(", ")}</p>
              )}
            </div>
            {/* Config JSON */}
            <div className="overflow-hidden">
              <p className="text-xs font-medium mb-1">Configuration:</p>
              <pre className="text-xs whitespace-pre-wrap break-words overflow-x-auto max-w-full">
                {JSON.stringify(version.config, null, 2)}
              </pre>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
