"use client";

import { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface MinimalistIconButtonProps {
  icon: LucideIcon;
  tooltip: string;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}

export function MinimalistIconButton({
  icon: Icon,
  tooltip,
  onClick,
  disabled = false,
  className,
}: MinimalistIconButtonProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClick}
            disabled={disabled}
            className={cn(
              "h-8 w-8 p-0 text-muted-foreground/60 hover:text-foreground hover:bg-transparent transition-colors",
              disabled && "opacity-50 cursor-not-allowed",
              className
            )}
          >
            <Icon className="h-5 w-5" />
            <span className="sr-only">{tooltip}</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{tooltip}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
} 