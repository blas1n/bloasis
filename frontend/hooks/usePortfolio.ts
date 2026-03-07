"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import client from "@/lib/api-client";
import type { PortfolioSummary, Position } from "@/lib/api-types";

interface UsePortfolioResult {
  summary: PortfolioSummary | null;
  positions: Position[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function usePortfolio(userId: string): UsePortfolioResult {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isInitialLoad = useRef(true);

  const fetchData = useCallback(async () => {
    // Skip fetch if userId is empty (component in props-only mode)
    if (!userId) return;

    // Only show loading skeleton on initial load
    if (isInitialLoad.current) {
      setIsLoading(true);
    }
    setError(null);

    // Auto-sync with Alpaca on first load (fire-and-forget on subsequent polls)
    if (isInitialLoad.current) {
      await client
        .POST("/v1/portfolios/{user_id}/sync", {
          params: { path: { user_id: userId } },
        })
        .catch(() => {});
    }

    const [summaryRes, positionsRes] = await Promise.all([
      client.GET("/v1/portfolios/{user_id}", {
        params: { path: { user_id: userId } },
      }),
      client.GET("/v1/portfolios/{user_id}/positions", {
        params: { path: { user_id: userId } },
      }),
    ]);

    if (summaryRes.error || positionsRes.error) {
      setError("Failed to load portfolio data");
    } else {
      setSummary((prev) => {
        // Runtime data is camelCase (CamelJSONResponse), cast accordingly
        const next = (summaryRes.data as unknown as PortfolioSummary) ?? null;
        return JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
      });
      setPositions((prev) => {
        const rawPositions = positionsRes.data?.positions || [];
        const next = rawPositions as unknown as Position[];
        return JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
      });
    }

    setIsLoading(false);
    isInitialLoad.current = false;
  }, [userId]);

  useEffect(() => {
    if (!userId) {
      setIsLoading(false);
      return;
    }

    fetchData();

    // Refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return { summary, positions, isLoading, error, refetch: fetchData };
}
