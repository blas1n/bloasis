"use client";

import { useState, useEffect, useCallback } from "react";
import client from "@/lib/api-client";
import type { Signal } from "@/lib/api-types";

interface UseSignalsResult {
  signals: Signal[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useSignals(userId: string): UseSignalsResult {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    const { data, error: apiError } = await client.GET(
      "/v1/users/{user_id}/signals",
      {
        params: { path: { user_id: userId } },
      }
    );

    if (apiError) {
      setError("Failed to load signals");
    } else {
      // Runtime data is camelCase (CamelJSONResponse), cast accordingly
      const rawSignals = data?.signals || [];
      setSignals(rawSignals as unknown as Signal[]);
    }

    setIsLoading(false);
  }, [userId]);

  useEffect(() => {
    fetchData();

    // Refresh every 5 minutes
    const interval = setInterval(fetchData, 300000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return { signals, isLoading, error, refetch: fetchData };
}
