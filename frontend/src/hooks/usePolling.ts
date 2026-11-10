import { useEffect, useRef, useState, useCallback } from 'react';
import { ApiError } from '../api/client';

interface UsePollingOptions<T> {
  intervalMs?: number;
  shouldStop?: (data: T) => boolean;
  enabled?: boolean;
}

export function usePolling<T>(
  fetcher: () => Promise<T>,
  options: UsePollingOptions<T> = {},
) {
  const { intervalMs = 2000, shouldStop, enabled = true } = options;

  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [isPolling, setIsPolling] = useState<boolean>(false);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const shouldStopRef = useRef(shouldStop);
  shouldStopRef.current = shouldStop;

  const timerRef = useRef<number | null>(null);
  const isTabVisibleRef = useRef<boolean>(!document.hidden);

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const poll = useCallback(async () => {
    if (!isTabVisibleRef.current) {
      return;
    }

    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
      setIsLoading(false);

      if (shouldStopRef.current && shouldStopRef.current(result)) {
        stopPolling();
        return;
      }

      timerRef.current = window.setTimeout(poll, intervalMs);
    } catch (err: unknown) {
      setIsLoading(false);
      const apiError =
        err instanceof ApiError
          ? err
          : new ApiError(err instanceof Error ? err.message : 'Polling failed', 500);
      setError(apiError);

      // Stop on fatal errors (401, 403, 404)
      if (apiError.status === 401 || apiError.status === 403 || apiError.status === 404) {
        stopPolling();
      } else {
        // Backoff for temporary errors
        timerRef.current = window.setTimeout(poll, intervalMs * 2);
      }
    }
  }, [intervalMs, stopPolling]);

  const refresh = useCallback(async () => {
    stopPolling();
    setIsLoading(true);
    await poll();
  }, [poll, stopPolling]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      isTabVisibleRef.current = !document.hidden;
      if (isTabVisibleRef.current && enabled && isPolling) {
        poll();
      } else if (!isTabVisibleRef.current) {
        if (timerRef.current !== null) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [enabled, isPolling, poll]);

  useEffect(() => {
    if (!enabled) {
      stopPolling();
      return;
    }

    setIsPolling(true);
    poll();

    return () => {
      stopPolling();
    };
  }, [enabled, poll, stopPolling]);

  return {
    data,
    isLoading,
    error,
    isPolling,
    refresh,
    setData,
  };
}
