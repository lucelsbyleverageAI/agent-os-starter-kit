"use client";

import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { useUsageData } from "./hooks/use-usage-data";
import { useUsageBreakdown } from "./hooks/use-usage-breakdown";
import { UsageSummaryCards } from "./components/usage-summary-cards";
import { CostByModelTable, CostByAgentTable, CostByUserTable } from "./components/cost-breakdown-table";
import { UsageChart } from "./components/usage-chart";
import { PeriodSelector } from "./components/period-selector";
import { cn } from "@/lib/utils";

export default function UsageInterface() {
  // OpenRouter aggregate data (credit balance, daily/weekly/monthly)
  const { data: openRouterData, loading: openRouterLoading, error: openRouterError, refetch: refetchOpenRouter } = useUsageData();

  // Detailed breakdown data from LangConnect
  const {
    summary,
    groupedTimeseries,
    loading: breakdownLoading,
    error: breakdownError,
    period,
    setPeriod,
    groupBy,
    setGroupBy,
    refetch: refetchBreakdown,
  } = useUsageBreakdown();

  const handleRefresh = async () => {
    await Promise.all([refetchOpenRouter(), refetchBreakdown()]);
  };

  const isLoading = openRouterLoading || breakdownLoading;

  return (
    <div className="container mx-auto px-4 md:px-8 lg:px-12 py-6">
      <PageHeader
        title="Usage & Costs"
        description="Monitor your OpenRouter API spending and credit usage"
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isLoading}
          >
            <RefreshCw className={cn("mr-2 h-4 w-4", isLoading && "animate-spin")} />
            Refresh
          </Button>
        }
      />

      {/* OpenRouter Credit Balance Cards */}
      <div className="mt-6">
        <UsageSummaryCards
          data={openRouterData}
          loading={openRouterLoading}
          error={openRouterError}
        />
      </div>

      {/* Period Selector for Breakdown Data */}
      <div className="mt-8 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Detailed Breakdown</h2>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* Cost Over Time Chart */}
      <div className="mt-4">
        <UsageChart
          data={groupedTimeseries?.data || []}
          groups={groupedTimeseries?.groups || []}
          loading={breakdownLoading}
          groupBy={groupBy}
          onGroupByChange={setGroupBy}
        />
      </div>

      {/* Cost Breakdown Tables */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <CostByModelTable
          data={summary?.by_model || []}
          loading={breakdownLoading}
        />
        <CostByAgentTable
          data={summary?.by_agent || []}
          loading={breakdownLoading}
        />
      </div>

      {/* Admin-only User Breakdown */}
      {summary?.by_user && summary.by_user.length > 0 && (
        <div className="mt-6">
          <CostByUserTable
            data={summary.by_user}
            loading={breakdownLoading}
          />
        </div>
      )}

      {/* Info Card */}
      {!breakdownLoading && !breakdownError && (
        <div className="mt-8">
          <div className="rounded-lg border bg-card p-6">
            <h3 className="text-lg font-semibold mb-4">About Usage Tracking</h3>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>
                This dashboard shows your OpenRouter API usage with detailed breakdowns.
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li><strong>Credit Balance:</strong> Your OpenRouter account credits (from OpenRouter API)</li>
                <li><strong>Cost by Model:</strong> Breakdown of costs by each LLM model used</li>
                <li><strong>Cost by Agent:</strong> Breakdown of costs by agent type</li>
                {summary?.by_user && summary.by_user.length > 0 && (
                  <li><strong>Cost by User:</strong> Admin view of costs per platform user</li>
                )}
              </ul>
              <p className="pt-2 border-t">
                All times are in UTC. Costs are tracked per agent run and aggregated for reporting.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
