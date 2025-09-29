import * as React from "react";

import {
  Card,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tool } from "@/types/tool";
import { ToolDetailsDialog } from "../tool-details-dialog";
import { Eye, FlaskConical } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { MinimalistIconButton } from "@/components/ui/minimalist-icon-button";
import NextLink from "next/link";
import _ from "lodash";

interface ToolCardProps {
  tool: Tool;
  showToolkit?: boolean;
}

export function ToolCard({ tool, showToolkit = false }: ToolCardProps) {
  return (
    <Card className="overflow-hidden relative group h-44 flex flex-col transition-all duration-300 ease-out hover:border-primary hover:border-2 hover:shadow-lg hover:shadow-primary/10 vibrate-on-hover">
      {/* Fixed Header - Small portion at top */}
      <CardHeader className="px-6 h-3 flex-shrink-0 flex items-center">
        <div className="flex items-center justify-between gap-3 w-full min-w-0">
          <CardTitle className="text-sm font-medium text-foreground min-w-0 flex-1">
            {/* Tool Name - truncate with ellipses */}
            <span className="truncate block">{_.startCase(tool.name)}</span>
          </CardTitle>
        </div>
      </CardHeader>
      
      {/* Description Area - Controlled middle space */}
      <div className="px-6 flex-1 min-h-0 -mt-1 flex flex-col gap-2">
        {tool.description ? (
          <p className="text-muted-foreground text-sm leading-5 overflow-hidden text-ellipsis" 
             style={{ 
               display: '-webkit-box', 
               WebkitLineClamp: showToolkit ? 2 : 3, 
               WebkitBoxOrient: 'vertical' 
             }}>
            {tool.description}
          </p>
        ) : (
          <p className="text-muted-foreground/50 text-sm italic">No description provided</p>
        )}
        
        {/* Toolkit Badge */}
        {showToolkit && tool.toolkit_display_name && (
          <div className="mt-auto">
            <span className="h-6 inline-flex items-center rounded-md bg-muted/50 px-2 text-xs text-muted-foreground/70">
              {tool.toolkit_display_name}
            </span>
          </div>
        )}
      </div>
      
      {/* Fixed Footer - Small portion at bottom */}
      <CardFooter className="flex w-full justify-end items-center h-3 px-6 flex-shrink-0 gap-1">
        <NextLink href={`/tools/playground?tool=${tool.name}`}>
          <MinimalistIconButton
            icon={FlaskConical}
            tooltip="Test in Playground"
          />
        </NextLink>
        <ToolDetailsDialog tool={tool}>
          <MinimalistIconButton
            icon={Eye}
            tooltip="View Tool Details"
          />
        </ToolDetailsDialog>
      </CardFooter>
    </Card>
  );
}

export function ToolCardLoading() {
  return (
    <Card className="overflow-hidden relative group h-44 flex flex-col transition-all duration-300 ease-out hover:border-primary hover:border-2 hover:shadow-lg hover:shadow-primary/10">
      {/* Fixed Header - Small portion at top */}
      <CardHeader className="px-6 h-3 flex-shrink-0 flex items-center">
        <div className="flex items-center justify-between gap-3 w-full min-w-0">
          <Skeleton className="h-5 w-3/4" />
        </div>
      </CardHeader>
      
      {/* Description Area - Controlled middle space */}
      <div className="px-6 flex-1 min-h-0 -mt-1">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
      
      {/* Fixed Footer - Small portion at bottom */}
      <CardFooter className="flex w-full justify-end items-center h-3 px-6 flex-shrink-0 gap-1">
        <Skeleton className="h-8 w-8 rounded" />
        <Skeleton className="h-8 w-8 rounded" />
      </CardFooter>
    </Card>
  );
}
