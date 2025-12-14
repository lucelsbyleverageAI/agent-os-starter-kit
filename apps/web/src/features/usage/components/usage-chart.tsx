"use client";

import { useState, useRef, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GroupedDailyUsageItem, GroupBy } from "../hooks/use-usage-breakdown";

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

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-US", { day: "numeric" });
}

function formatFullDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric"
  });
}

function formatCost(value: number): string {
  if (value >= 1) {
    return `$${value.toFixed(2)}`;
  }
  if (value === 0) {
    return "$0";
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

interface TooltipData {
  item: GroupedDailyUsageItem;
  x: number;
  y: number;
}

function ChartTooltip({
  item,
  x,
  y,
  groupColorMap
}: {
  item: GroupedDailyUsageItem;
  x: number;
  y: number;
  groupColorMap: Map<string, string>;
}) {
  // Sort breakdown by cost descending
  const sortedBreakdown = Object.entries(item.breakdown)
    .sort(([, a], [, b]) => b - a);

  return (
    <div
      className="absolute z-50 pointer-events-none bg-popover border rounded-lg shadow-lg p-3 min-w-[200px]"
      style={{
        left: `${x}px`,
        top: `${y}px`,
        transform: "translate(-50%, -100%)",
        marginTop: "-8px"
      }}
    >
      <div className="text-sm font-medium border-b pb-2 mb-2">
        {formatFullDate(item.date)}
      </div>
      {sortedBreakdown.length > 0 ? (
        <>
          <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
            {sortedBreakdown.map(([group, cost]) => (
              <div key={group} className="flex items-center justify-between gap-4 text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className="w-2.5 h-2.5 rounded-sm shrink-0"
                    style={{ backgroundColor: groupColorMap.get(group) }}
                  />
                  <span className="text-muted-foreground truncate">
                    {shortenGroupName(group)}
                  </span>
                </div>
                <span className="font-mono text-xs shrink-0">
                  {formatCost(cost)}
                </span>
              </div>
            ))}
          </div>
          <div className="border-t mt-2 pt-2 flex justify-between text-sm font-medium">
            <span>Total</span>
            <span className="font-mono">{formatCost(item.total_cost)}</span>
          </div>
        </>
      ) : (
        <div className="text-sm text-muted-foreground">No usage</div>
      )}
    </div>
  );
}

export function UsageChart({ data, groups, loading, groupBy, onGroupByChange }: UsageChartProps) {
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const chartRef = useRef<HTMLDivElement>(null);

  // Track previous data to show during loading
  const [displayData, setDisplayData] = useState(data);
  const [displayGroups, setDisplayGroups] = useState(groups);

  // Update display data when new data arrives (not during loading)
  useEffect(() => {
    if (!loading && data) {
      setDisplayData(data);
      setDisplayGroups(groups);
    }
  }, [data, groups, loading]);

  // Close tooltip when clicking outside or when loading
  useEffect(() => {
    const handleClickOutside = () => setTooltip(null);
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, []);

  // Clear tooltip when loading starts
  useEffect(() => {
    if (loading) {
      setTooltip(null);
    }
  }, [loading]);

  // Create a consistent color mapping for groups
  const groupColorMap = new Map<string, string>();
  displayGroups.forEach((group, index) => {
    groupColorMap.set(group, getGroupColor(index));
  });

  const totalCost = displayData.reduce((sum, d) => sum + d.total_cost, 0);
  const maxCost = Math.max(...displayData.map((d) => d.total_cost), 0.0001);

  const handleBarHover = (
    item: GroupedDailyUsageItem,
    event: React.MouseEvent<HTMLDivElement>
  ) => {
    event.stopPropagation();
    if (!chartRef.current) return;

    const rect = chartRef.current.getBoundingClientRect();
    const barRect = event.currentTarget.getBoundingClientRect();

    setTooltip({
      item,
      x: barRect.left - rect.left + barRect.width / 2,
      y: barRect.top - rect.top,
    });
  };

  const handleBarLeave = () => {
    setTooltip(null);
  };

  // Calculate which date labels to show and how to format them
  const getDateLabel = (dateStr: string, index: number): string | null => {
    const date = new Date(dateStr);
    const day = date.getDate();
    const dataLength = displayData.length;

    // For longer ranges, show fewer labels
    if (dataLength > 31) {
      // Show only 1st and 15th of each month
      if (day === 1) return formatDate(dateStr);
      if (day === 15) return formatShortDate(dateStr);
      return null;
    }

    if (dataLength > 14) {
      // Show 1st of month with month name, otherwise show every 5th day
      if (day === 1) return formatDate(dateStr);
      if (index % 5 === 0) return formatShortDate(dateStr);
      return null;
    }

    if (dataLength > 7) {
      // Show 1st of month with month name, otherwise show every 3rd day
      if (day === 1) return formatDate(dateStr);
      if (index % 3 === 0) return formatShortDate(dateStr);
      return null;
    }

    // For 7 days or less, show all dates with full format
    return formatDate(dateStr);
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Cost Over Time</CardTitle>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">
              Total: {formatCost(totalCost)}
            </span>
            <Tabs value={groupBy} onValueChange={(v) => onGroupByChange(v as GroupBy)}>
              <TabsList variant="branded">
                <TabsTrigger value="model">Model</TabsTrigger>
                <TabsTrigger value="agent">Agent</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {displayData.length === 0 && !loading ? (
          <div className="h-48 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">
              No usage data yet. Start using agents to see cost trends.
            </p>
          </div>
        ) : (
          <div className="relative" ref={chartRef}>
            {/* Loading overlay */}
            {loading && (
              <div className="absolute inset-0 bg-background/60 backdrop-blur-[1px] z-40 flex items-center justify-center rounded-lg transition-opacity duration-200">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                  <span>Loading...</span>
                </div>
              </div>
            )}
            {tooltip && !loading && (
              <ChartTooltip
                item={tooltip.item}
                x={tooltip.x}
                y={tooltip.y}
                groupColorMap={groupColorMap}
              />
            )}
            <div className="flex gap-2">
              {/* Y-axis labels */}
              <div className="flex flex-col justify-between h-48 text-[10px] text-muted-foreground pr-1 shrink-0 w-14 text-right">
                <span>{formatCost(maxCost)}</span>
                <span>{formatCost(maxCost / 2)}</span>
                <span>$0</span>
              </div>
              {/* Chart area */}
              <div className="flex-1 flex flex-col min-w-0">
                <div
                  style={{ height: "192px" }}
                  className="flex items-end gap-[2px]"
                >
                  {displayData.map((item, index) => {
                    const chartHeight = 192;
                    const barHeight = item.total_cost > 0
                      ? Math.max((item.total_cost / maxCost) * chartHeight, 2)
                      : 0;

                    return (
                      <div
                        key={item.date}
                        className="flex-1 min-w-0 h-full flex flex-col justify-end cursor-pointer group"
                        onMouseEnter={(e) => !loading && handleBarHover(item, e)}
                        onMouseLeave={handleBarLeave}
                      >
                        {/* Stacked bar */}
                        {barHeight > 0 ? (
                          <div
                            className="w-full flex flex-col-reverse rounded-t overflow-hidden transition-opacity group-hover:opacity-80"
                            style={{ height: `${barHeight}px` }}
                          >
                            {displayGroups.map((group) => {
                              const cost = item.breakdown[group] || 0;
                              if (cost === 0) return null;
                              const segmentHeight = (cost / item.total_cost) * barHeight;
                              return (
                                <div
                                  key={group}
                                  className="w-full"
                                  style={{
                                    height: `${segmentHeight}px`,
                                    minHeight: "1px",
                                    backgroundColor: groupColorMap.get(group),
                                  }}
                                />
                              );
                            })}
                          </div>
                        ) : (
                          // Empty placeholder for days with no data
                          <div className="w-full h-1 bg-muted/30 rounded-t" />
                        )}
                      </div>
                    );
                  })}
                </div>
                {/* X-axis labels */}
                <div className="flex gap-[2px] mt-1">
                  {displayData.map((item, index) => {
                    const label = getDateLabel(item.date, index);
                    return (
                      <div key={item.date} className="flex-1 text-center min-w-0">
                        {label && (
                          <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                            {label}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Legend */}
            {displayGroups.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1">
                {displayGroups.map((group) => (
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
          </div>
        )}
      </CardContent>
    </Card>
  );
}
