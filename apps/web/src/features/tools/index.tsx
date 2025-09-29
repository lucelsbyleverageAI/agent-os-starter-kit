"use client";

import React from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToolKitsList } from "./components/toolkits-list";
import { AllToolsList } from "./components/all-tools-list";

/**
 * The parent component containing the tools interface with tabs.
 */
export default function ToolsInterface(): React.ReactNode {
  return (
    <div className="flex w-full flex-col gap-6">
      <Tabs defaultValue="toolkits" className="w-full">
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="toolkits">Toolkits</TabsTrigger>
          <TabsTrigger value="all-tools">All Tools</TabsTrigger>
        </TabsList>

        <TabsContent value="toolkits" className="mt-6">
          <ToolKitsList />
        </TabsContent>

        <TabsContent value="all-tools" className="mt-6">
          <AllToolsList />
        </TabsContent>
      </Tabs>
    </div>
  );
}
