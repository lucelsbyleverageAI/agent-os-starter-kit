"use client";

import { useState } from "react";
import { MoreHorizontal, Users, Trash2, Upload, Sparkles, Crown, Edit, Eye, Package, Globe, Download } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Skeleton } from "@/components/ui/skeleton";
import { MinimalistBadge, MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import type { Skill } from "@/types/skill";

// Permission icon mapping
function getPermissionIconAndTooltip(permissionLevel?: string, isPublic?: boolean) {
  if (isPublic) {
    return {
      icon: Globe,
      tooltip: "Public - Available to all users",
    };
  }
  switch (permissionLevel) {
    case "owner":
      return {
        icon: Crown,
        tooltip: "Owner - Full access and management permissions",
      };
    case "editor":
      return {
        icon: Edit,
        tooltip: "Editor - Can view and update skill",
      };
    case "viewer":
      return {
        icon: Eye,
        tooltip: "Viewer - Can only view skill",
      };
    default:
      return {
        icon: Eye,
        tooltip: "View access",
      };
  }
}

interface SkillCardProps {
  skill: Skill;
  onUpdate?: (skill: Skill) => void;
  onDelete?: (skill: Skill) => void;
  onShare?: (skill: Skill) => void;
  onDownload?: (skill: Skill) => void;
}

export function SkillCard({
  skill,
  onUpdate,
  onDelete,
  onShare,
  onDownload,
}: SkillCardProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const canEdit = skill.permission_level === "owner" || skill.permission_level === "editor";
  const canDelete = skill.permission_level === "owner";
  const canShare = skill.permission_level === "owner";

  const permissionDisplay = getPermissionIconAndTooltip(skill.permission_level ?? undefined, skill.is_public);
  const pipCount = skill.pip_requirements?.length || 0;

  return (
    <Card className="group relative flex flex-col items-start gap-3 p-6 transition-all hover:border-primary hover:shadow-md vibrate-on-hover">
      {/* Three-dots menu - absolute positioned in top-right */}
      {(canEdit || canDelete || canShare || onDownload) && (
        <div className="absolute right-3 top-3 opacity-0 group-hover:opacity-100 transition-opacity">
          <DropdownMenu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
              >
                <MoreHorizontal className="h-4 w-4" />
                <span className="sr-only">Open menu</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {onDownload && (
                <DropdownMenuItem onClick={() => onDownload(skill)}>
                  <Download className="mr-2 h-4 w-4" />
                  Download
                </DropdownMenuItem>
              )}
              {canEdit && onUpdate && (
                <DropdownMenuItem onClick={() => onUpdate(skill)}>
                  <Upload className="mr-2 h-4 w-4" />
                  Update
                </DropdownMenuItem>
              )}
              {canShare && onShare && (
                <DropdownMenuItem onClick={() => onShare(skill)}>
                  <Users className="mr-2 h-4 w-4" />
                  Manage Access
                </DropdownMenuItem>
              )}
              {canDelete && onDelete && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() => onDelete(skill)}
                    className="text-destructive focus:text-destructive"
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Delete
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      {/* Icon and title */}
      <div className="flex items-center gap-3 w-full">
        <div className="bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-md">
          <Sparkles className="text-muted-foreground h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h4 className="font-semibold leading-none truncate">{skill.name}</h4>
        </div>
      </div>

      {/* Description - Fixed 3 lines with tooltip for full text */}
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <p className="text-muted-foreground line-clamp-3 text-sm w-full min-h-[3.75rem] cursor-default">
              {skill.description || "No description"}
            </p>
          </TooltipTrigger>
          {skill.description && skill.description.length > 100 && (
            <TooltipContent side="bottom" className="max-w-sm">
              <p className="text-sm">{skill.description}</p>
            </TooltipContent>
          )}
        </Tooltip>
      </TooltipProvider>

      {/* Divider */}
      <div className="w-full border-t border-border" />

      {/* Footer with badges */}
      <div className="flex w-full items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <MinimalistBadge
            icon={permissionDisplay.icon}
            tooltip={permissionDisplay.tooltip}
          />
          {pipCount > 0 && (
            <MinimalistBadgeWithText
              icon={Package}
              tooltip={`${pipCount} pip ${pipCount === 1 ? 'package' : 'packages'} required`}
              text={`${pipCount}`}
            />
          )}
        </div>
      </div>
    </Card>
  );
}

export function SkillCardLoading() {
  return (
    <Card className="relative flex flex-col items-start gap-3 p-6">
      {/* Icon and title */}
      <div className="flex items-center gap-3 w-full">
        <Skeleton className="h-10 w-10 rounded-md" />
        <Skeleton className="h-5 w-3/4" />
      </div>

      {/* Description */}
      <div className="w-full space-y-2">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>

      {/* Divider */}
      <div className="w-full border-t border-border" />

      {/* Footer */}
      <div className="flex w-full items-center gap-2">
        <Skeleton className="h-6 w-6 rounded-md" />
        <Skeleton className="h-6 w-12 rounded-md" />
      </div>
    </Card>
  );
}
