"use client";

import { LucideIcon } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface MinimalistBadgeProps {
  icon: LucideIcon;
  tooltip: string;
  className?: string;
}

interface MinimalistBadgeWithTextProps {
  icon: LucideIcon;
  text: string;
  tooltip?: string;
  className?: string;
}

export function MinimalistBadge({
  icon: Icon,
  tooltip,
  className,
}: MinimalistBadgeProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div
            className={cn(
              "inline-flex items-center justify-center h-6 w-6 rounded-md bg-muted/30 text-muted-foreground hover:bg-muted/50 transition-colors duration-150",
              className
            )}
          >
            <Icon className="h-4 w-4" />
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p>{tooltip}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function MinimalistBadgeWithText({
  icon: Icon,
  text,
  tooltip,
  className,
}: MinimalistBadgeWithTextProps) {
  const badgeContent = (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 h-6 px-2 rounded-md bg-muted/30 text-muted-foreground hover:bg-muted/50 text-xs font-medium transition-colors duration-150",
        className
      )}
    >
      <Icon className="h-3 w-3" />
      {text}
    </div>
  );

  if (tooltip) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            {badgeContent}
          </TooltipTrigger>
          <TooltipContent>
            <p>{tooltip}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return badgeContent;
} 