"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { Signal } from "@/lib/types";

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

    const result = await api.getPersonalizedStrategy(userId);

    if (result.error) {
      setError(result.error);
    } else {
      setSignals(result.data?.signals || []);
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
