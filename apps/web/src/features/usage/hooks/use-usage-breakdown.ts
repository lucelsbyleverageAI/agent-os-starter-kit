import { useState, useCallback, useEffect } from 'react';
import { useAuthContext } from '@/providers/Auth';
import { subDays, startOfDay, endOfDay, format } from 'date-fns';
import { DateRange } from 'react-day-picker';

export interface UsageAggregateItem {
  name: string;
  display_name?: string;
  run_count: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_cost: number;
}

export interface UsageSummary {
  by_model: UsageAggregateItem[];
  by_agent: UsageAggregateItem[];
  by_user?: UsageAggregateItem[];
  total_cost: number;
  total_tokens: number;
  total_runs: number;
  period_start: string;
  period_end: string;
}

export interface DailyUsageItem {
  date: string;
  cost: number;
  tokens: number;
  runs: number;
}

export interface GroupedDailyUsageItem {
  date: string;
  breakdown: Record<string, number>;
  total_cost: number;
  runs: number;
}

export interface TimeSeriesData {
  data: DailyUsageItem[];
  period_start: string;
  period_end: string;
}

export interface GroupedTimeSeriesData {
  data: GroupedDailyUsageItem[];
  groups: string[];
  period_start: string;
  period_end: string;
}

export type GroupBy = 'model' | 'agent';

// Default date range: last 30 days
function getDefaultDateRange(): DateRange {
  const today = new Date();
  return {
    from: startOfDay(subDays(today, 29)),
    to: endOfDay(today),
  };
}

interface UseUsageBreakdownReturn {
  summary: UsageSummary | null;
  timeseries: TimeSeriesData | null;
  groupedTimeseries: GroupedTimeSeriesData | null;
  loading: boolean;
  error: string | null;
  dateRange: DateRange | undefined;
  setDateRange: (range: DateRange | undefined) => void;
  groupBy: GroupBy;
  setGroupBy: (groupBy: GroupBy) => void;
  refetch: () => Promise<void>;
}

export function useUsageBreakdown(): UseUsageBreakdownReturn {
  const { session, isLoading: authLoading } = useAuthContext();
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [timeseries, setTimeseries] = useState<TimeSeriesData | null>(null);
  const [groupedTimeseries, setGroupedTimeseries] = useState<GroupedTimeSeriesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState<DateRange | undefined>(getDefaultDateRange());
  const [groupBy, setGroupBy] = useState<GroupBy>('model');

  const fetchUsageBreakdown = useCallback(async () => {
    if (authLoading || !session?.accessToken) {
      return;
    }

    if (!dateRange?.from || !dateRange?.to) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Format dates as ISO strings (date only, no time)
      const startDate = format(dateRange.from, 'yyyy-MM-dd');
      const endDate = format(dateRange.to, 'yyyy-MM-dd');

      // Fetch summary, timeseries, and grouped timeseries in parallel
      const [summaryResponse, timeseriesResponse, groupedResponse] = await Promise.all([
        fetch(`/api/langconnect/usage/summary?start_date=${startDate}&end_date=${endDate}`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
          credentials: 'include',
        }),
        fetch(`/api/langconnect/usage/timeseries?start_date=${startDate}&end_date=${endDate}`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
          credentials: 'include',
        }),
        fetch(`/api/langconnect/usage/timeseries/grouped?start_date=${startDate}&end_date=${endDate}&group_by=${groupBy}`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
          credentials: 'include',
        }),
      ]);

      if (!summaryResponse.ok) {
        // If 404, it means no usage data yet - not an error
        if (summaryResponse.status === 404) {
          setSummary({
            by_model: [],
            by_agent: [],
            total_cost: 0,
            total_tokens: 0,
            total_runs: 0,
            period_start: new Date().toISOString(),
            period_end: new Date().toISOString(),
          });
          setTimeseries({ data: [], period_start: '', period_end: '' });
          setGroupedTimeseries({ data: [], groups: [], period_start: '', period_end: '' });
          return;
        }
        const errorData = await summaryResponse.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to fetch usage summary: ${summaryResponse.status}`);
      }

      const summaryData = await summaryResponse.json();
      setSummary(summaryData);

      if (timeseriesResponse.ok) {
        const timeseriesData = await timeseriesResponse.json();
        setTimeseries(timeseriesData);
      } else {
        setTimeseries({ data: [], period_start: '', period_end: '' });
      }

      if (groupedResponse.ok) {
        const groupedData = await groupedResponse.json();
        setGroupedTimeseries(groupedData);
      } else {
        setGroupedTimeseries({ data: [], groups: [], period_start: '', period_end: '' });
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch usage breakdown';
      setError(errorMessage);
      console.error('Error fetching usage breakdown:', err);
    } finally {
      setLoading(false);
    }
  }, [session?.accessToken, authLoading, dateRange, groupBy]);

  useEffect(() => {
    fetchUsageBreakdown();
  }, [fetchUsageBreakdown]);

  return {
    summary,
    timeseries,
    groupedTimeseries,
    loading,
    error,
    dateRange,
    setDateRange,
    groupBy,
    setGroupBy,
    refetch: fetchUsageBreakdown,
  };
}
