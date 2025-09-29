"use client";

import React, { useState } from "react";
import { useMCPContext } from "@/providers/MCP";
import { ToolkitCard } from "./toolkit-card";
import { ToolkitsLoading } from "./toolkits-loading";
import { Search } from "@/components/ui/tool-search";

export function ToolKitsList() {
  const { toolkits, loading } = useMCPContext();
  const [openToolkits, setOpenToolkits] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState("");

  const toggleToolkit = (toolkitName: string) => {
    setOpenToolkits(prev => {
      const newSet = new Set(prev);
      if (newSet.has(toolkitName)) {
        newSet.delete(toolkitName);
      } else {
        newSet.add(toolkitName);
      }
      return newSet;
    });
  };

  const filteredToolkits = toolkits.filter(toolkit =>
    toolkit.display_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    toolkit.tools.some(tool => 
      tool.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (tool.description && tool.description.toLowerCase().includes(searchTerm.toLowerCase()))
    )
  );

  if (loading && !toolkits.length) {
    return <ToolkitsLoading />;
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <div className="flex w-full items-center justify-start">
        <Search
          onSearchChange={setSearchTerm}
          placeholder="Search toolkits and tools..."
          className="w-full md:w-[calc(50%-0.5rem)] lg:w-[calc(33.333%-0.667rem)]"
        />
      </div>

      <div className="flex flex-col gap-4">
        {filteredToolkits.map((toolkit) => (
          <ToolkitCard
            key={toolkit.name}
            toolkit={toolkit}
            toggleToolkit={toggleToolkit}
            isOpen={openToolkits.has(toolkit.name)}
          />
        ))}
        {filteredToolkits.length === 0 && searchTerm && (
          <p className="my-4 w-full text-center text-sm text-slate-500">
            No toolkits found matching "{searchTerm}".
          </p>
        )}
        {toolkits.length === 0 && !searchTerm && !loading && (
          <p className="my-4 w-full text-center text-sm text-slate-500">
            No toolkits available.
          </p>
        )}
      </div>
    </div>
  );
} 