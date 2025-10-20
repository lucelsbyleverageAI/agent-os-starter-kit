import * as React from "react";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tool } from "@/types/tool";
import { ToolDetailsDialog } from "../tool-details-dialog";
import { Wrench } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import NextLink from "next/link";
import _ from "lodash";

interface ToolCardProps {
  tool: Tool;
  showToolkit?: boolean;
}

export function ToolCard({ tool, showToolkit = false }: ToolCardProps) {
  return (
    <Card className="group relative flex flex-col items-start gap-2.5 px-4 py-3 transition-all hover:border-primary hover:shadow-md vibrate-on-hover">
      {/* Icon and title */}
      <div className="flex items-center gap-3 w-full">
        <div className="bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-md">
          <Wrench className="text-muted-foreground h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h4 className="font-semibold leading-none">{_.startCase(tool.name)}</h4>
        </div>
      </div>

      {/* Description - Fixed 3 lines */}
      <p className="text-muted-foreground line-clamp-3 text-sm w-full min-h-[3.75rem]">
        {tool.description || "No description provided"}
      </p>

      {/* Toolkit Badge */}
      {showToolkit && tool.toolkit_display_name && (
        <Badge variant="outline" className="text-xs">
          {tool.toolkit_display_name}
        </Badge>
      )}

      {/* Divider */}
      <div className="w-full border-t border-border" />

      {/* Footer with buttons */}
      <div className="flex w-full items-center gap-2">
        <NextLink href={`/tools/playground?tool=${tool.name}`} className="cursor-pointer">
          <Button variant="default" size="sm" className="h-8 cursor-pointer">
            Playground
          </Button>
        </NextLink>
        <ToolDetailsDialog tool={tool}>
          <Button variant="outline" size="sm" className="h-8 cursor-pointer">
            View Schema
          </Button>
        </ToolDetailsDialog>
      </div>
    </Card>
  );
}

export function ToolCardLoading() {
  return (
    <Card className="relative flex flex-col items-start gap-2.5 px-4 py-3">
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

      {/* Buttons */}
      <div className="flex w-full items-center gap-2">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-8 w-28" />
      </div>
    </Card>
  );
}
