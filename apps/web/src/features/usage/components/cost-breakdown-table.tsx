"use client";

import { useState, useEffect } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UsageAggregateItem } from "../hooks/use-usage-breakdown";
import { cn } from "@/lib/utils";

interface CostBreakdownTableProps {
  title: string;
  description?: string;
  data: UsageAggregateItem[];
  loading: boolean;
  showPercentage?: boolean;
  emptyMessage?: string;
  nameFormatter?: (item: UsageAggregateItem) => string;
}

function formatCost(value: number): string {
  if (value >= 1) {
    return `$${value.toFixed(2)}`;
  }
  if (value >= 0.01) {
    return `$${value.toFixed(4)}`;
  }
  return `$${value.toFixed(6)}`;
}

function formatTokens(value: number): string {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return value.toString();
}

function extractModelDisplayName(modelName: string): string {
  // Extract just the model name from provider/model format
  const parts = modelName.split("/");
  if (parts.length > 1) {
    // Capitalize first letter and format nicely
    const model = parts[1];
    return model
      .split("-")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  }
  return modelName;
}

function extractProvider(modelName: string): string {
  const parts = modelName.split("/");
  if (parts.length > 1) {
    const provider = parts[0];
    // Capitalize first letter
    return provider.charAt(0).toUpperCase() + provider.slice(1);
  }
  return "";
}

export function CostBreakdownTable({
  title,
  description,
  data,
  loading,
  showPercentage = true,
  emptyMessage = "No usage data available for this period",
  nameFormatter,
}: CostBreakdownTableProps) {
  // Track previous data to show during loading
  const [displayData, setDisplayData] = useState(data);

  // Update display data when new data arrives (not during loading)
  useEffect(() => {
    if (!loading && data) {
      setDisplayData(data);
    }
  }, [data, loading]);

  const totalCost = displayData.reduce((sum, item) => sum + item.total_cost, 0);

  // Show empty state only if no data and not loading
  if (displayData.length === 0 && !loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">{title}</CardTitle>
          {description && (
            <p className="text-sm text-muted-foreground">{description}</p>
          )}
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground text-center py-8">
            {emptyMessage}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </CardHeader>
      <CardContent>
        <div className="relative">
          {/* Loading overlay */}
          {loading && (
            <div className="absolute inset-0 bg-background/60 backdrop-blur-[1px] z-10 flex items-center justify-center rounded-lg transition-opacity duration-200">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                <span>Loading...</span>
              </div>
            </div>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Runs</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                {showPercentage && (
                  <TableHead className="text-right w-[100px]">Share</TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {displayData.map((item, index) => {
                const percentage =
                  totalCost > 0 ? (item.total_cost / totalCost) * 100 : 0;
                const displayName = nameFormatter
                  ? nameFormatter(item)
                  : item.display_name || item.name;

                return (
                  <TableRow key={item.name || index}>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium">{displayName}</span>
                        {!nameFormatter && item.name.includes("/") && (
                          <span className="text-xs text-muted-foreground">
                            {extractProvider(item.name)}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">{item.run_count}</TableCell>
                    <TableCell className="text-right">
                      {formatTokens(item.total_tokens)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatCost(item.total_cost)}
                    </TableCell>
                    {showPercentage && (
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-12 h-2 rounded-full bg-secondary overflow-hidden">
                            <div
                              className={cn(
                                "h-full rounded-full transition-all",
                                percentage > 50
                                  ? "bg-primary"
                                  : percentage > 25
                                    ? "bg-primary/70"
                                    : "bg-primary/50"
                              )}
                              style={{ width: `${Math.min(percentage, 100)}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground w-12">
                            {percentage.toFixed(1)}%
                          </span>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// Specialized components for specific breakdown types

export function CostByModelTable({
  data,
  loading,
}: {
  data: UsageAggregateItem[];
  loading: boolean;
}) {
  return (
    <CostBreakdownTable
      title="Cost by Model"
      description="Usage breakdown by LLM model"
      data={data}
      loading={loading}
      nameFormatter={(item) => extractModelDisplayName(item.name)}
      emptyMessage="No model usage data yet. Start using agents to see cost breakdowns."
    />
  );
}

export function CostByAgentTable({
  data,
  loading,
}: {
  data: UsageAggregateItem[];
  loading: boolean;
}) {
  return (
    <CostBreakdownTable
      title="Cost by Agent"
      description="Usage breakdown by agent type"
      data={data}
      loading={loading}
      nameFormatter={(item) => {
        if (item.display_name) return item.display_name;
        // Format graph_name nicely
        return item.name
          .split("_")
          .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
          .join(" ");
      }}
      emptyMessage="No agent usage data yet. Start using agents to see cost breakdowns."
    />
  );
}

export function CostByUserTable({
  data,
  loading,
}: {
  data: UsageAggregateItem[];
  loading: boolean;
}) {
  return (
    <CostBreakdownTable
      title="Cost by User"
      description="Usage breakdown by platform user (Admin only)"
      data={data}
      loading={loading}
      nameFormatter={(item) => item.display_name || item.name}
      emptyMessage="No user usage data yet."
    />
  );
}
