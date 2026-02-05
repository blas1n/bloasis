"use client";

import { useState, useEffect, useCallback } from "react";
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

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    const [summaryRes, positionsRes] = await Promise.all([
      api.getPortfolioSummary(userId),
      api.getPositions(userId),
    ]);

    if (summaryRes.error || positionsRes.error) {
      setError(summaryRes.error || positionsRes.error || "Unknown error");
    } else {
      setSummary(summaryRes.data);
      setPositions(positionsRes.data?.positions || []);
    }

    setIsLoading(false);
  }, [userId]);

  useEffect(() => {
    fetchData();

    // Refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return { summary, positions, isLoading, error, refetch: fetchData };
}
