"use client";

import React from "react";
import { ChevronRightIcon } from "lucide-react";
import { ToolCard, ToolCardLoading } from "./tool-card";
import { useMCPContext } from "@/providers/MCP";
import { Button } from "@/components/ui/button";
import { Search } from "@/components/ui/tool-search";
import { useSearchTools } from "@/hooks/use-search-tools";

/**
 * Component for displaying all tools in a searchable grid.
 */
export function AllToolsList(): React.ReactNode {
  const { tools, loading, getTools, cursor, setTools } = useMCPContext();
  const { toolSearchTerm, debouncedSetSearchTerm, filteredTools } =
    useSearchTools(tools);
  const [loadingMore, setLoadingMore] = React.useState(false);

  const handleLoadMore = async () => {
    if (!cursor) return;

    setLoadingMore(true);
    try {
      const newTools = await getTools(cursor);
      setTools((prevTools) => [...prevTools, ...newTools]);
    } catch (error) {
      console.error("Error loading more tools:", error);
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <div className="flex w-full items-center justify-start">
        <Search
          onSearchChange={debouncedSetSearchTerm}
          placeholder="Search tools..."
          className="w-full md:w-[calc(50%-0.5rem)] lg:w-[calc(33.333%-0.667rem)]"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {loading &&
          !filteredTools.length &&
          Array.from({ length: 6 }).map((_, index) => (
            <ToolCardLoading key={`tool-card-loading-${index}`} />
          ))}
        {filteredTools.map((tool, index) => (
          <ToolCard
            key={`${tool.name}-${index}`}
            tool={tool}
            showToolkit={true} // Show toolkit since we're not grouped
          />
        ))}
        {filteredTools.length === 0 && toolSearchTerm && (
          <p className="my-4 w-full text-center text-sm text-slate-500">
            No tools found matching "{toolSearchTerm}".
          </p>
        )}
        {tools.length === 0 && !toolSearchTerm && !loading && (
          <p className="my-4 w-full text-center text-sm text-slate-500">
            No tools available for this agent.
          </p>
        )}
      </div>

      {!toolSearchTerm && cursor && (
        <div className="mt-4 flex justify-center">
          <Button
            onClick={handleLoadMore}
            disabled={loadingMore}
            variant="outline"
            className="gap-1 px-2.5"
          >
            {loadingMore ? "Loading..." : "Load More Tools"}
            <ChevronRightIcon className="h-4 w-4" />
          </Button>
        </div>
      )}

      {loadingMore && (
        <div className="mt-4 flex justify-center">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <ToolCardLoading key={`tool-card-loading-more-${index}`} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
} 