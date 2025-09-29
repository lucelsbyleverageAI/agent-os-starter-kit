"use client";

import React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Toolkit } from "@/types/tool";
import { ToolList } from "./tool-list";
import { cn } from "@/lib/utils";
import _ from "lodash";

interface ToolkitCardProps {
  toolkit: Toolkit;
  toggleToolkit: (name: string) => void;
  isOpen: boolean;
}

export function ToolkitCard({ toolkit, toggleToolkit, isOpen }: ToolkitCardProps) {
  return (
    <Card
      className={cn(
        "overflow-hidden",
        isOpen ? "" : "hover:bg-accent/50 cursor-pointer transition-colors"
      )}
      onClick={() => {
        if (isOpen) return;
        toggleToolkit(toolkit.name);
      }}
    >
      <Collapsible
        open={isOpen}
        onOpenChange={() => toggleToolkit(toolkit.name)}
      >
        <CardHeader className="flex flex-row items-center bg-inherit">
          <div className="flex-1">
            <div className="flex items-center">
              <CollapsibleTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="mr-2 h-8 w-8 p-0"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    toggleToolkit(toolkit.name);
                  }}
                >
                  {isOpen ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                  <span className="sr-only">Toggle</span>
                </Button>
              </CollapsibleTrigger>
              <CardTitle className="flex items-center gap-2">
                <p className="text-2xl">{toolkit.display_name}</p>
              </CardTitle>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-6 inline-flex items-center rounded-md bg-muted/50 px-2 text-xs text-muted-foreground/70">
              {toolkit.count} Tool{toolkit.count === 1 ? "" : "s"}
            </span>
          </div>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="pt-6">
            <ToolList tools={toolkit.tools} />
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
} 