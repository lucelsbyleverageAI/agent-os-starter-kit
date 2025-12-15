"use client";

import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { useUsageData } from "./hooks/use-usage-data";
import { useUsageBreakdown } from "./hooks/use-usage-breakdown";
import { UsageSummaryCards } from "./components/usage-summary-cards";
import { CostByModelTable, CostByAgentTable, CostByUserTable } from "./components/cost-breakdown-table";
import { UsageChart } from "./components/usage-chart";
import { DateRangePicker } from "./components/date-range-picker";
import { cn } from "@/lib/utils";
import { RoleGuard, useUserRole } from "@/providers/UserRole";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

function AccessDeniedRedirect() {
  const router = useRouter();
  const { loading, roleValidated } = useUserRole();

  useEffect(() => {
    if (!loading && roleValidated) {
      router.replace("/");
    }
  }, [loading, roleValidated, router]);

  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-4"></div>
        <p className="text-muted-foreground">Redirecting...</p>
      </div>
    </div>
  );
}

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-4"></div>
        <p className="text-muted-foreground">Verifying permissions...</p>
      </div>
    </div>
  );
}

function UsageFallback() {
  const { loading, roleValidated } = useUserRole();

  if (loading || !roleValidated) {
    return <LoadingFallback />;
  }

  return <AccessDeniedRedirect />;
}

function UsageInterface() {
  // OpenRouter aggregate data (credit balance, daily/weekly/monthly)
  const { data: openRouterData, loading: openRouterLoading, error: openRouterError, refetch: refetchOpenRouter } = useUsageData();

  // Detailed breakdown data from LangConnect
  const {
    summary,
    groupedTimeseries,
    loading: breakdownLoading,
    dateRange,
    setDateRange,
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

      {/* Date Range Picker for Breakdown Data */}
      <div className="mt-8 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Detailed Breakdown</h2>
        <DateRangePicker value={dateRange} onChange={setDateRange} />
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
    </div>
  );
}

export function UsageFeature() {
  return (
    <RoleGuard roles={['dev_admin', 'business_admin']} fallback={<UsageFallback />}>
      <UsageInterface />
    </RoleGuard>
  );
}

export default UsageFeature;
