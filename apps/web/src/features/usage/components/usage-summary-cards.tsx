"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UsageData } from "../hooks/use-usage-data";
import { Calendar, CalendarDays, CalendarRange, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface UsageSummaryCardsProps {
  data: UsageData | null;
  loading: boolean;
  error: string | null;
}

function formatCredits(value: number): string {
  if (value >= 1) {
    return `$${value.toFixed(2)}`;
  }
  return `$${value.toFixed(4)}`;
}

function UsageCard({
  title,
  value,
  subtitle,
  icon: Icon,
  loading,
  className,
}: {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ElementType;
  loading: boolean;
  className?: string;
}) {
  return (
    <Card className={cn("relative overflow-hidden", className)}>
      {/* Loading overlay */}
      {loading && (
        <div className="absolute inset-0 bg-background/60 backdrop-blur-[1px] z-10 flex items-center justify-center transition-opacity duration-200">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </CardContent>
    </Card>
  );
}

export function UsageSummaryCards({ data, loading, error }: UsageSummaryCardsProps) {
  // Track previous data to show during loading
  const [displayData, setDisplayData] = useState<UsageData | null>(data);

  // Update display data when new data arrives (not during loading)
  useEffect(() => {
    if (!loading && data) {
      setDisplayData(data);
    }
  }, [data, loading]);

  if (error) {
    return (
      <Card className="border-destructive/50 bg-destructive/5">
        <CardContent className="pt-6">
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span className="font-medium">Failed to load usage data</span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <UsageCard
        title="Today"
        value={displayData ? formatCredits(displayData.usage_daily) : "$0.00"}
        subtitle="Credits used today (UTC)"
        icon={Calendar}
        loading={loading}
      />
      <UsageCard
        title="This Week"
        value={displayData ? formatCredits(displayData.usage_weekly) : "$0.00"}
        subtitle="Credits used this week"
        icon={CalendarDays}
        loading={loading}
      />
      <UsageCard
        title="This Month"
        value={displayData ? formatCredits(displayData.usage_monthly) : "$0.00"}
        subtitle="Credits used this month"
        icon={CalendarRange}
        loading={loading}
      />
    </div>
  );
}
