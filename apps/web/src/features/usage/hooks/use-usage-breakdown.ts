import { useState, useCallback, useEffect } from 'react';
import { useAuthContext } from '@/providers/Auth';

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

export type UsagePeriod = 'day' | 'week' | 'month' | 'all';
export type GroupBy = 'model' | 'agent';

interface UseUsageBreakdownReturn {
  summary: UsageSummary | null;
  timeseries: TimeSeriesData | null;
  groupedTimeseries: GroupedTimeSeriesData | null;
  loading: boolean;
  error: string | null;
  period: UsagePeriod;
  setPeriod: (period: UsagePeriod) => void;
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
  const [period, setPeriod] = useState<UsagePeriod>('month');
  const [groupBy, setGroupBy] = useState<GroupBy>('model');

  const fetchUsageBreakdown = useCallback(async () => {
    if (authLoading || !session?.accessToken) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Fetch summary, timeseries, and grouped timeseries in parallel
      const [summaryResponse, timeseriesResponse, groupedResponse] = await Promise.all([
        fetch(`/api/langconnect/usage/summary?period=${period}`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
          credentials: 'include',
        }),
        fetch(`/api/langconnect/usage/timeseries?period=${period}`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${session.accessToken}`,
          },
          credentials: 'include',
        }),
        fetch(`/api/langconnect/usage/timeseries/grouped?period=${period}&group_by=${groupBy}`, {
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
  }, [session?.accessToken, authLoading, period, groupBy]);

  useEffect(() => {
    fetchUsageBreakdown();
  }, [fetchUsageBreakdown]);

  return {
    summary,
    timeseries,
    groupedTimeseries,
    loading,
    error,
    period,
    setPeriod,
    groupBy,
    setGroupBy,
    refetch: fetchUsageBreakdown,
  };
}
