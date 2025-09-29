"use client";

import { ChevronDown, ChevronRight, LucideIcon } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Button } from "@/components/ui/button";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { CompactUserCard } from "@/components/ui/compact-user-card";
import { cn } from "@/lib/utils";

interface User {
  userId: string;
  name: string;
  email: string;
  initials: string;
  isCurrentUser?: boolean;
  canRemove?: boolean;
}

interface PermissionLevelSectionProps {
  icon: LucideIcon;
  label: string;
  tooltip: string;
  count: number;
  users: User[];
  isExpanded: boolean;
  onToggle: () => void;
  onRemoveUser: (userId: string, userName: string) => void;
  className?: string;
  sectionClassName?: string;
}

export function PermissionLevelSection({
  icon,
  label,
  tooltip,
  count,
  users,
  isExpanded,
  onToggle,
  onRemoveUser,
  className,
  sectionClassName,
}: PermissionLevelSectionProps) {
  if (count === 0) {
    return null;
  }

  return (
    <Collapsible open={isExpanded} onOpenChange={onToggle} className={className}>
      <CollapsibleTrigger asChild>
        <Button
          variant="ghost"
          className={cn(
            "w-full justify-between p-3 h-auto border rounded-lg hover:bg-muted/50",
            className
          )}
        >
          <div className="flex items-center gap-3">
            <MinimalistBadgeWithText
              icon={icon}
              text={`${label} (${count})`}
              tooltip={tooltip}
            />
          </div>
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2">
        <div className={cn(
          "pl-4 space-y-1",
          sectionClassName
        )}>
          {users.length === 0 ? (
            <div className="py-2 text-sm text-muted-foreground">
              No users in this permission level
            </div>
          ) : (
            users.map((user) => (
              <CompactUserCard
                key={user.userId}
                userId={user.userId}
                name={user.name}
                email={user.email}
                initials={user.initials}
                isCurrentUser={user.isCurrentUser}
                canRemove={user.canRemove}
                onRemove={() => onRemoveUser(user.userId, user.name)}
                variant="list"
              />
            ))
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
} 