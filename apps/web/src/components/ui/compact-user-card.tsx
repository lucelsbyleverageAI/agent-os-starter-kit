"use client";

import { UserX } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface CompactUserCardProps {
  userId: string;
  name: string;
  email: string;
  initials: string;
  isCurrentUser?: boolean;
  canRemove?: boolean;
  onRemove?: () => void;
  className?: string;
  variant?: "default" | "minimal" | "list";
}

export function CompactUserCard({
  userId,
  name,
  email,
  initials,
  isCurrentUser = false,
  canRemove = true,
  onRemove,
  className,
  variant = "default",
}: CompactUserCardProps) {
  const baseClasses = "flex items-center justify-between transition-colors";
  
  const variantClasses = {
    default: "py-2 px-3 rounded-lg hover:bg-muted/50",
    minimal: "py-1 px-2 hover:bg-muted/30",
    list: "py-1 hover:bg-muted/20",
  };

  const avatarSize = {
    default: "h-6 w-6",
    minimal: "h-5 w-5", 
    list: "h-4 w-4",
  };

  return (
    <div
      className={cn(
        baseClasses,
        variantClasses[variant],
        isCurrentUser && "bg-muted/50",
        className
      )}
    >
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <Avatar className={cn("shrink-0", avatarSize[variant])}>
          <AvatarFallback className={variant === "list" ? "text-xs" : "text-xs"}>
            {initials}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className={cn(
              "font-medium truncate",
              variant === "list" ? "text-xs" : "text-sm"
            )}>
              {name}
            </p>
            {isCurrentUser && (
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                (You)
              </span>
            )}
          </div>
          {email !== name && variant !== "list" && (
            <p className="text-xs text-muted-foreground truncate">
              {email}
            </p>
          )}
        </div>
      </div>
      {canRemove && !isCurrentUser && onRemove && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onRemove}
          className={cn(
            "text-red-600 hover:text-red-700 hover:bg-red-50 shrink-0",
            variant === "list" ? "h-4 w-4 p-0" : "h-6 w-6 p-0"
          )}
        >
          <UserX className={variant === "list" ? "h-2 w-2" : "h-3 w-3"} />
        </Button>
      )}
    </div>
  );
} 