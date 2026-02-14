import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { Trade } from "@/lib/types";

export function useTradeHistory(userId: string, limit: number = 50) {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTrades = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await api.getTradeHistory(userId, limit);
      setTrades(response.trades);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load trades");
    } finally {
      setIsLoading(false);
    }
  }, [userId, limit]);

  useEffect(() => {
    fetchTrades();
  }, [fetchTrades]);

  return { trades, isLoading, error, refetch: fetchTrades };
}
