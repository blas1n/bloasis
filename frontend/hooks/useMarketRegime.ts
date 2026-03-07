"use client";

import { useState, useEffect, useCallback } from "react";
import client from "@/lib/api-client";
import type { MarketRegime } from "@/lib/api-types";

interface UseMarketRegimeResult {
  regime: MarketRegime | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useMarketRegime(): UseMarketRegimeResult {
  const [regime, setRegime] = useState<MarketRegime | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    const { data, error: apiError } = await client.GET(
      "/v1/market/regimes/current"
    );

    if (apiError) {
      setError("Failed to load market regime");
    } else if (data) {
      // Runtime data is camelCase (CamelJSONResponse), cast accordingly
      setRegime(data as unknown as MarketRegime);
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
