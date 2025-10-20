"use client";

import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as React from "react";

import { cn } from "@/lib/utils";

function Tabs({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  );
}

export type TabsListVariant = "default" | "branded";

interface TabsListProps extends React.ComponentProps<typeof TabsPrimitive.List> {
  variant?: TabsListVariant;
}

const TabsListContext = React.createContext<TabsListVariant>("default");

function TabsList({
  className,
  variant = "default",
  ...props
}: TabsListProps) {
  return (
    <TabsListContext.Provider value={variant}>
      <TabsPrimitive.List
        data-slot="tabs-list"
        className={cn(
          "inline-flex w-fit items-center justify-center flex-shrink-0",
          // Default variant
          variant === "default" && "h-10 bg-muted/30 p-1 rounded-lg gap-1",
          // Branded variant - light gray background container with spacing
          variant === "branded" && "bg-muted/40 p-1 rounded-lg gap-1",
          className,
        )}
        {...props}
      />
    </TabsListContext.Provider>
  );
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  const variant = React.useContext(TabsListContext);

  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm font-medium whitespace-nowrap transition-all duration-200",
        "focus-visible:outline-ring focus-visible:outline-2 focus-visible:outline-offset-2",
        "disabled:pointer-events-none disabled:opacity-50",
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        // Default variant styles
        variant === "default" && [
          "rounded-md",
          "text-muted-foreground hover:text-foreground hover:bg-background/50",
          "data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-xs",
        ],
        // Branded variant styles - pill buttons in gray container
        variant === "branded" && [
          "rounded-md",
          "text-foreground/70 hover:text-foreground",
          "data-[state=active]:bg-primary data-[state=active]:text-primary-foreground",
          "data-[state=active]:shadow-sm",
        ],
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("flex-1 outline-none", className)}
      {...props}
    />
  );
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
