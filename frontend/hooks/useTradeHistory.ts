import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { Trade } from "@/lib/types";

const DEFAULT_POLL_MS = 5000;

export function useTradeHistory(userId: string, limit: number = 50) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchTrades = useCallback(async () => {
    try {
      setError(null);
      const response = await api.getTradeHistory(userId, { limit });
      if (response.error) {
        setError(response.error);
        timeoutRef.current = setTimeout(fetchTrades, DEFAULT_POLL_MS);
      } else if (response.data) {
        setTrades(response.data.trades);
        timeoutRef.current = setTimeout(
          fetchTrades,
          response.data.nextPollMs ?? DEFAULT_POLL_MS
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load trades");
      timeoutRef.current = setTimeout(fetchTrades, DEFAULT_POLL_MS);
    } finally {
      setIsLoading(false);
    }
  }, [userId, limit]);

  useEffect(() => {
    fetchTrades();
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [fetchTrades]);

  return { trades, isLoading, error, refetch: fetchTrades, fetchTrades };
}
