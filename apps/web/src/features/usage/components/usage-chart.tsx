"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { GroupedDailyUsageItem, GroupBy } from "../hooks/use-usage-breakdown";
import { cn } from "@/lib/utils";

interface UsageChartProps {
  data: GroupedDailyUsageItem[];
  groups: string[];
  loading: boolean;
  groupBy: GroupBy;
  onGroupByChange: (groupBy: GroupBy) => void;
}

// Color palette for different groups - using explicit colors
const COLORS = [
  "#2563eb", // blue
  "#16a34a", // green
  "#dc2626", // red
  "#ca8a04", // yellow
  "#9333ea", // purple
  "#0891b2", // cyan
  "#ea580c", // orange
  "#db2777", // pink
  "#4f46e5", // indigo
  "#059669", // emerald
];

function getGroupColor(index: number): string {
  return COLORS[index % COLORS.length];
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatCost(value: number): string {
  if (value >= 1) {
    return `$${value.toFixed(2)}`;
  }
  return `$${value.toFixed(4)}`;
}

function shortenGroupName(name: string): string {
  // For model names like "anthropic/claude-3.5-sonnet", show just the model part
  if (name.includes("/")) {
    const parts = name.split("/");
    return parts[parts.length - 1];
  }
  // Truncate long names
  if (name.length > 20) {
    return name.substring(0, 17) + "...";
  }
  return name;
}

export function UsageChart({ data, groups, loading, groupBy, onGroupByChange }: UsageChartProps) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Cost Over Time</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Cost Over Time</CardTitle>
            <div className="flex rounded-md border">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onGroupByChange("model")}
                className={cn(
                  "rounded-r-none border-r",
                  groupBy === "model" && "bg-muted"
                )}
              >
                Model
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onGroupByChange("agent")}
                className={cn(
                  "rounded-l-none",
                  groupBy === "agent" && "bg-muted"
                )}
              >
                Agent
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-48 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">
              No usage data yet. Start using agents to see cost trends.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const maxCost = Math.max(...data.map((d) => d.total_cost), 0.01);
  const totalCost = data.reduce((sum, d) => sum + d.total_cost, 0);

  // Create a consistent color mapping for groups
  const groupColorMap = new Map<string, string>();
  groups.forEach((group, index) => {
    groupColorMap.set(group, getGroupColor(index));
  });

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Cost Over Time</CardTitle>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">
              Total: {formatCost(totalCost)}
            </span>
            <div className="flex rounded-md border">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onGroupByChange("model")}
                className={cn(
                  "rounded-r-none border-r",
                  groupBy === "model" && "bg-muted"
                )}
              >
                Model
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onGroupByChange("agent")}
                className={cn(
                  "rounded-l-none",
                  groupBy === "agent" && "bg-muted"
                )}
              >
                Agent
              </Button>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex gap-2">
          {/* Y-axis labels */}
          <div className="flex flex-col justify-between h-48 text-[10px] text-muted-foreground pr-1 shrink-0">
            <span>{formatCost(maxCost)}</span>
            <span>{formatCost(maxCost / 2)}</span>
            <span>$0</span>
          </div>
          {/* Chart area */}
          <div className="flex-1 flex flex-col min-w-0">
            <div style={{ height: "192px", display: "flex", alignItems: "flex-end", gap: "4px" }}>
              {data.map((item) => {
                // Use pixel heights (192px chart height)
                const chartHeight = 192;
                const barHeight = Math.max((item.total_cost / maxCost) * chartHeight, 4);
                return (
                  <div
                    key={item.date}
                    className="flex-1 group min-w-0"
                    style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "flex-end" }}
                  >
                    {/* Stacked bar */}
                    <div
                      className="w-full flex flex-col-reverse rounded-t overflow-hidden cursor-pointer"
                      style={{ height: `${barHeight}px` }}
                      title={`${formatDate(item.date)}: ${formatCost(item.total_cost)} (${item.runs} runs)`}
                    >
                      {groups.map((group) => {
                        const cost = item.breakdown[group] || 0;
                        if (cost === 0) return null;
                        const segmentHeight = (cost / item.total_cost) * barHeight;
                        return (
                          <div
                            key={group}
                            className="w-full transition-all hover:opacity-80"
                            style={{
                              height: `${segmentHeight}px`,
                              backgroundColor: groupColorMap.get(group),
                            }}
                            title={`${shortenGroupName(group)}: ${formatCost(cost)}`}
                          />
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
            {/* X-axis labels */}
            <div className="flex gap-1 mt-1">
              {data.map((item, index) => (
                <div key={item.date} className="flex-1 text-center min-w-0">
                  {(data.length <= 7 || index % Math.ceil(data.length / 7) === 0) && (
                    <span className="text-[10px] text-muted-foreground truncate block">
                      {formatDate(item.date)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Legend */}
        {groups.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1">
            {groups.map((group) => (
              <div key={group} className="flex items-center gap-1.5 text-xs">
                <div
                  className="w-3 h-3 rounded-sm shrink-0"
                  style={{ backgroundColor: groupColorMap.get(group) }}
                />
                <span className="text-muted-foreground truncate max-w-[150px]" title={group}>
                  {shortenGroupName(group)}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
