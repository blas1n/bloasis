"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import type { TradingStatus, TradingControlResponse } from "@/lib/types";

const DEFAULT_POLL_MS = 5000;

export function useTradingControl(userId: string) {
  const [status, setStatus] = useState<TradingStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleNextPoll = useCallback((ms: number, fn: () => void) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(fn, ms);
  }, []);

  const fetchStatus = useCallback(async () => {
    setError(null);
    const { data, error: apiError } = await api.getTradingStatus(userId);

    if (apiError) {
      setError(apiError);
      setIsLoading(false);
      scheduleNextPoll(DEFAULT_POLL_MS, fetchStatus);
      return;
    }

    if (data) {
      setStatus(data);
      scheduleNextPoll(data.nextPollMs ?? DEFAULT_POLL_MS, fetchStatus);
    }

    setIsLoading(false);
  }, [userId, scheduleNextPoll]);

  const startTrading = useCallback(async (): Promise<TradingControlResponse | null> => {
    setIsLoading(true);
    setError(null);

    const { data, error: apiError } = await api.startTrading(userId);

    if (apiError) {
      setError(apiError);
      setIsLoading(false);
      return null;
    }

    // Immediately re-fetch to get new status + updated nextPollMs (active → 3s)
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    await fetchStatus();
    setIsLoading(false);
    return data;
  }, [userId, fetchStatus]);

  const stopTrading = useCallback(async (
    mode: "hard" | "soft" = "soft"
  ): Promise<TradingControlResponse | null> => {
    setIsLoading(true);
    setError(null);

    const { data, error: apiError } = await api.stopTrading(userId, mode);

    if (apiError) {
      setError(apiError);
      setIsLoading(false);
      return null;
    }

    // Immediately re-fetch to get new status + updated nextPollMs (inactive → 10s)
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    await fetchStatus();
    setIsLoading(false);
    return data;
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
    fetchStatus,
    startTrading,
    stopTrading,
  };
}
