"use client";

import { Crown, Edit, Eye, Users } from "lucide-react";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { cn } from "@/lib/utils";

interface PermissionCount {
  owners: number;
  editors: number;
  viewers: number;
}

interface PermissionSummaryHeaderProps {
  counts: PermissionCount;
  className?: string;
}

export function PermissionSummaryHeader({
  counts,
  className,
}: PermissionSummaryHeaderProps) {
  const totalUsers = counts.owners + counts.editors + counts.viewers;

  if (totalUsers === 0) {
    return (
      <div className={cn("text-center py-6 text-muted-foreground", className)}>
        <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p className="text-sm">No users have access to this resource</p>
        <p className="text-xs">Add team members to start collaborating</p>
      </div>
    );
  }

  return (
    <div className={cn("flex items-center justify-between p-3 bg-muted/25 rounded-lg border", className)}>
      <div className="flex items-center gap-2">
        <Users className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">
          {totalUsers} user{totalUsers !== 1 ? 's' : ''} with access
        </span>
      </div>
      <div className="flex items-center gap-2">
        {counts.owners > 0 && (
          <MinimalistBadgeWithText
            icon={Crown}
            text={counts.owners.toString()}
            tooltip={`${counts.owners} owner${counts.owners !== 1 ? 's' : ''}`}
          />
        )}
        {counts.editors > 0 && (
          <MinimalistBadgeWithText
            icon={Edit}
            text={counts.editors.toString()}
            tooltip={`${counts.editors} editor${counts.editors !== 1 ? 's' : ''}`}
          />
        )}
        {counts.viewers > 0 && (
          <MinimalistBadgeWithText
            icon={Eye}
            text={counts.viewers.toString()}
            tooltip={`${counts.viewers} viewer${counts.viewers !== 1 ? 's' : ''}`}
          />
        )}
      </div>
    </div>
  );
} 