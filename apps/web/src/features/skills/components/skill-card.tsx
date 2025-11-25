"use client";

import { useState } from "react";
import { MoreHorizontal, Share2, Trash2, Upload, Globe } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import type { Skill } from "@/types/skill";

interface SkillCardProps {
  skill: Skill;
  onUpdate?: (skill: Skill) => void;
  onDelete?: (skill: Skill) => void;
  onShare?: (skill: Skill) => void;
}

export function SkillCard({
  skill,
  onUpdate,
  onDelete,
  onShare,
}: SkillCardProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const canEdit = skill.permission_level === "owner" || skill.permission_level === "editor";
  const canDelete = skill.permission_level === "owner";
  const canShare = skill.permission_level === "owner";

  const getPermissionBadgeVariant = () => {
    if (skill.is_public) return "default";
    switch (skill.permission_level) {
      case "owner":
        return "default";
      case "editor":
        return "secondary";
      case "viewer":
        return "outline";
      default:
        return "outline";
    }
  };

  const getPermissionLabel = () => {
    if (skill.is_public) return "Public";
    return skill.permission_level || "viewer";
  };

  return (
    <Card className="group relative overflow-hidden transition-shadow hover:shadow-md">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <CardTitle className="flex items-center gap-2 text-base font-mono">
              <span className="truncate">{skill.name}</span>
              {skill.is_public && (
                <Globe className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
              )}
            </CardTitle>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge variant={getPermissionBadgeVariant()} className="capitalize text-xs">
              {getPermissionLabel()}
            </Badge>
            {(canEdit || canDelete || canShare) && (
              <DropdownMenu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                    <span className="sr-only">Open menu</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {canEdit && onUpdate && (
                    <DropdownMenuItem onClick={() => onUpdate(skill)}>
                      <Upload className="mr-2 h-4 w-4" />
                      Update
                    </DropdownMenuItem>
                  )}
                  {canShare && onShare && (
                    <DropdownMenuItem onClick={() => onShare(skill)}>
                      <Share2 className="mr-2 h-4 w-4" />
                      Share
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
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <CardDescription className="line-clamp-3 text-sm">
          {skill.description}
        </CardDescription>
        {skill.pip_requirements && skill.pip_requirements.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
            {skill.pip_requirements.slice(0, 3).map((pkg) => (
              <Badge key={pkg} variant="outline" className="text-xs">
                {pkg}
              </Badge>
            ))}
            {skill.pip_requirements.length > 3 && (
              <Badge variant="outline" className="text-xs">
                +{skill.pip_requirements.length - 3} more
              </Badge>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function SkillCardLoading() {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-5 w-16" />
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </CardContent>
    </Card>
  );
}
