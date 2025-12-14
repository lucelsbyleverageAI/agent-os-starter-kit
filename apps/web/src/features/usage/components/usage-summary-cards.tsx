"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
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
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <>
            <Skeleton className="h-8 w-24 mb-1" />
            {subtitle && <Skeleton className="h-4 w-32" />}
          </>
        ) : (
          <>
            <div className="text-2xl font-bold">{value}</div>
            {subtitle && (
              <p className="text-xs text-muted-foreground">{subtitle}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function UsageSummaryCards({ data, loading, error }: UsageSummaryCardsProps) {
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
        value={data ? formatCredits(data.usage_daily) : "$0.00"}
        subtitle="Credits used today (UTC)"
        icon={Calendar}
        loading={loading}
      />
      <UsageCard
        title="This Week"
        value={data ? formatCredits(data.usage_weekly) : "$0.00"}
        subtitle="Credits used this week"
        icon={CalendarDays}
        loading={loading}
      />
      <UsageCard
        title="This Month"
        value={data ? formatCredits(data.usage_monthly) : "$0.00"}
        subtitle="Credits used this month"
        icon={CalendarRange}
        loading={loading}
      />
    </div>
  );
}
