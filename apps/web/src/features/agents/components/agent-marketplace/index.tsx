"use client";

import { useMemo, useState } from "react";
import { Filter, Search, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AgentCard } from "../agent-card";
import { useAgentsContext } from "@/providers/Agents";
import { getDeployments } from "@/lib/environment/deployments";
import { GraphGroup } from "../../types";
import { groupAgentsByGraphs } from "@/lib/agent-utils";
import { getTagLabel } from "@/lib/agent-tags";

interface AgentMarketplaceProps {
  onCreateAgent: () => void;
}

export function AgentMarketplace({ onCreateAgent }: AgentMarketplaceProps) {
  const { agents, loading: agentsLoading } = useAgentsContext();
  const deployments = getDeployments();

  const [searchQuery, setSearchQuery] = useState("");
  const [tagFilter, setTagFilter] = useState<string>("all");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  // Extract all unique tags from agents
  const allTags = useMemo(() => {
    const tagsSet = new Set<string>();
    agents.forEach((agent) => {
      if (agent.tags && Array.isArray(agent.tags)) {
        agent.tags.forEach((tag) => tagsSet.add(tag));
      }
    });
    return Array.from(tagsSet).sort();
  }, [agents]);

  const allGraphGroups: GraphGroup[] = useMemo(() => {
    if (agentsLoading) return [];
    const groups: GraphGroup[] = [];
    deployments.forEach((deployment) => {
      const agentsInDeployment = agents.filter(
        (agent) => agent.deploymentId === deployment.id,
      );
      const agentsGroupedByGraphs = groupAgentsByGraphs(agentsInDeployment);
      agentsGroupedByGraphs.forEach((agentGroup) => {
        if (agentGroup.length > 0) {
          const graphId = agentGroup[0].graph_id;
          groups.push({
            agents: agentGroup,
            deployment,
            graphId,
          });
        }
      });
    });
    return groups;
  }, [agents, deployments, agentsLoading]);

  const filteredAgents = useMemo(() => {
    // 1. Get all agents from all groups
    let filteredAgentsList = allGraphGroups.flatMap((group) => group.agents);

    // 2. Filter by tag dropdown selection
    if (tagFilter !== "all") {
      filteredAgentsList = filteredAgentsList.filter((agent) => {
        if (!agent.tags || !Array.isArray(agent.tags)) return false;
        return agent.tags.includes(tagFilter);
      });
    }

    // 3. Filter by selected tag badges (multi-select)
    if (selectedTags.length > 0) {
      filteredAgentsList = filteredAgentsList.filter((agent) => {
        if (!agent.tags || !Array.isArray(agent.tags)) return false;
        // Agent must have at least one of the selected tags
        return selectedTags.some((selectedTag) =>
          agent.tags!.includes(selectedTag)
        );
      });
    }

    // 4. Filter by search query
    const lowerCaseQuery = searchQuery.toLowerCase();
    if (!lowerCaseQuery) {
      return filteredAgentsList;
    }

    return filteredAgentsList.filter((agent) =>
      agent.name.toLowerCase().includes(lowerCaseQuery) ||
      (agent.description && agent.description.toLowerCase().includes(lowerCaseQuery))
    );
  }, [allGraphGroups, tagFilter, searchQuery, selectedTags]);

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag)
        ? prev.filter((t) => t !== tag)
        : [...prev, tag]
    );
  };

  const clearAllFilters = () => {
    setSearchQuery("");
    setTagFilter("all");
    setSelectedTags([]);
  };

  const hasActiveFilters = searchQuery || tagFilter !== "all" || selectedTags.length > 0;

  return (
    <div className="space-y-6">
      {/* Search and Filters */}
      <div className="flex flex-col gap-4">
        {/* Search and Filter Row */}
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <div className="relative w-full max-w-sm">
            <Search className="text-muted-foreground absolute top-2.5 left-2.5 h-4 w-4" />
            <Input
              placeholder="Search agents..."
              className="pl-8"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Filter Dropdown */}
          <div className="flex items-center gap-2">
            <Filter className="text-muted-foreground h-4 w-4" />
            <Select
              value={tagFilter}
              onValueChange={setTagFilter}
            >
              <SelectTrigger className="h-10 min-w-[200px]">
                <SelectValue placeholder="All Tags" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Tags</SelectItem>
                {allTags.map((tag) => (
                  <SelectItem key={tag} value={tag}>
                    {getTagLabel(tag)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Clear Filters Button */}
          {hasActiveFilters && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearAllFilters}
              className="h-9 ml-auto"
            >
              Clear filters
            </Button>
          )}
        </div>

        {/* Tags Row */}
        {allTags.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2">
              <Tag className="text-muted-foreground h-4 w-4" />
              <span className="text-sm font-medium">Tags:</span>
            </div>
            {allTags.map((tag) => (
              <Badge
                key={tag}
                variant={selectedTags.includes(tag) ? "default" : "outline"}
                className="cursor-pointer"
                onClick={() => toggleTag(tag)}
              >
                {getTagLabel(tag)}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Results Count */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">
          {filteredAgents.length}{" "}
          {filteredAgents.length === 1 ? "Agent" : "Agents"}
        </h2>
      </div>

      {/* Agents Grid or Empty State */}
      {filteredAgents.length === 0 ? (
        <div className="animate-in fade-in-50 flex flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center">
          <div className="bg-muted mx-auto flex h-20 w-20 items-center justify-center rounded-full">
            <Search className="text-muted-foreground h-10 w-10" />
          </div>
          <h2 className="mt-6 text-xl font-semibold">No agents found</h2>
          <p className="text-muted-foreground mt-2 text-center max-w-md">
            {hasActiveFilters
              ? "We couldn't find any agents matching your search criteria. Try adjusting your filters or use the 'Create New Agent' button above."
              : "You don't have any agents yet. Use the 'Create New Agent' button above to get started."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {filteredAgents.map((agent) => (
            <AgentCard
              key={`agent-marketplace-${agent.assistant_id}`}
              agent={agent}
              showDeployment={true}
            />
          ))}
        </div>
      )}
    </div>
  );
}
