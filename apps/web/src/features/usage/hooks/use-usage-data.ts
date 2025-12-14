import { useState, useCallback, useEffect } from 'react';
import { toast } from 'sonner';

export interface UsageData {
  label: string;
  limit: number | null;
  limit_remaining: number | null;
  usage: number;
  usage_daily: number;
  usage_weekly: number;
  usage_monthly: number;
  is_free_tier: boolean;
}

interface UseUsageDataReturn {
  data: UsageData | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useUsageData(): UseUsageDataReturn {
  const [data, setData] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsageData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/openrouter/usage', {
        method: 'GET',
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `Failed to fetch usage data: ${response.status}`);
      }

      const result = await response.json();
      setData(result.data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch usage data';
      setError(errorMessage);
      console.error('Error fetching usage data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsageData();
  }, [fetchUsageData]);

  return {
    data,
    loading,
    error,
    refetch: fetchUsageData,
  };
}
