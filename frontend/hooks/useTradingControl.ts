"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import client from "@/lib/api-client";
import type { TradingStatus, TradingControlResponse } from "@/lib/api-types";

const DEFAULT_POLL_MS = 5000;

export function useTradingControl(userId: string) {
  const [status, setStatus] = useState<TradingStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [brokerNotConfigured, setBrokerNotConfigured] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleNextPoll = useCallback((ms: number, fn: () => void) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(fn, ms);
  }, []);

  const fetchStatus = useCallback(async () => {
    setError(null);
    const { data, error: apiError, response } = await client.GET(
      "/v1/users/{user_id}/trading",
      {
        params: { path: { user_id: userId } },
      }
    );

    if (apiError) {
      if (response?.status === 400) {
        setBrokerNotConfigured(true);
        setIsLoading(false);
        return;
      }
      setError("Failed to load trading status");
      setIsLoading(false);
      scheduleNextPoll(DEFAULT_POLL_MS, fetchStatus);
      return;
    }

    setBrokerNotConfigured(false);
    if (data) {
      // Runtime data is camelCase (CamelJSONResponse), cast accordingly
      setStatus(data as unknown as TradingStatus);
      scheduleNextPoll(DEFAULT_POLL_MS, fetchStatus);
    }

    setIsLoading(false);
  }, [userId, scheduleNextPoll]);

  const startTrading = useCallback(async (): Promise<TradingControlResponse | null> => {
    setIsLoading(true);
    setError(null);

    const { data, error: apiError } = await client.POST(
      "/v1/users/{user_id}/trading",
      {
        params: { path: { user_id: userId } },
      }
    );

    if (apiError) {
      setError("Failed to start trading");
      setIsLoading(false);
      return null;
    }

    // Immediately re-fetch to get new status + updated nextPollMs (active -> 3s)
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    await fetchStatus();
    setIsLoading(false);
    return (data as unknown as TradingControlResponse) ?? null;
  }, [userId, fetchStatus]);

  const stopTrading = useCallback(async (
    mode: "hard" | "soft" = "soft"
  ): Promise<TradingControlResponse | null> => {
    setIsLoading(true);
    setError(null);

    const { data, error: apiError } = await client.DELETE(
      "/v1/users/{user_id}/trading",
      {
        params: { path: { user_id: userId } },
        body: { mode },
      }
    );

    if (apiError) {
      setError("Failed to stop trading");
      setIsLoading(false);
      return null;
    }

    // Immediately re-fetch to get new status + updated nextPollMs (inactive -> 10s)
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    await fetchStatus();
    setIsLoading(false);
    return (data as unknown as TradingControlResponse) ?? null;
  }, [userId, fetchStatus]);

  useEffect(() => {
    setIsLoading(true);
    fetchStatus();
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [fetchStatus]);

  return {
    status,
    isLoading,
    error,
    brokerNotConfigured,
    fetchStatus,
    startTrading,
    stopTrading,
  };
}
