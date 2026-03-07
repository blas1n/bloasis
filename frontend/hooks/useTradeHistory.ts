import { useState, useEffect, useCallback, useRef } from "react";
import client from "@/lib/api-client";
import type { Trade, TradeHistoryResponse } from "@/lib/api-types";

const DEFAULT_POLL_MS = 5000;

export function useTradeHistory(userId: string, limit: number = 50) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchTrades = useCallback(async () => {
    try {
      setError(null);
      const { data, error: apiError } = await client.GET(
        "/v1/portfolios/{user_id}/trades",
        {
          params: {
            path: { user_id: userId },
            query: { limit },
          },
        }
      );
      if (apiError) {
        setError("Failed to load trades");
        timeoutRef.current = setTimeout(fetchTrades, DEFAULT_POLL_MS);
      } else if (data) {
        // Runtime data is camelCase (CamelJSONResponse), cast accordingly
        const camelData = data as unknown as TradeHistoryResponse;
        setTrades(camelData.trades);
        timeoutRef.current = setTimeout(fetchTrades, DEFAULT_POLL_MS);
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
