"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { MarketRegimeResponse } from "@/lib/types";

interface UseMarketRegimeResult {
  regime: MarketRegimeResponse | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useMarketRegime(): UseMarketRegimeResult {
  const [regime, setRegime] = useState<MarketRegimeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    const result = await api.getMarketRegime();

    if (result.error) {
      setError(result.error);
    } else {
      setRegime(result.data);
    }

    setIsLoading(false);
  }, []);

  useEffect(() => {
    fetchData();

    // Refresh every 5 minutes (regime is cached for 6 hours)
    const interval = setInterval(fetchData, 300000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return { regime, isLoading, error, refetch: fetchData };
}
