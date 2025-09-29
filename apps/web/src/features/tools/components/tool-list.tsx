"use client";

import React from "react";
import { Tool } from "@/types/tool";
import { ToolCard } from "./tool-card";

interface ToolListProps {
  tools: Tool[];
}

export function ToolList({ tools }: ToolListProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {tools.map((tool, index) => (
        <ToolCard
          key={`${tool.name}-${index}`}
          tool={tool}
          showToolkit={false} // Don't show toolkit since we're already grouped
        />
      ))}
    </div>
  );
} 