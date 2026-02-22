"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import type { PortfolioSummary, Position } from "@/lib/types";

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
      await api.syncWithAlpaca(userId).catch(() => {});
    }

    const [summaryRes, positionsRes] = await Promise.all([
      api.getPortfolioSummary(userId),
      api.getPositions(userId),
    ]);

    if (summaryRes.error || positionsRes.error) {
      setError(summaryRes.error || positionsRes.error || "Unknown error");
    } else {
      setSummary((prev) => {
        const next = summaryRes.data;
        return JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
      });
      setPositions((prev) => {
        const next = positionsRes.data?.positions || [];
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
