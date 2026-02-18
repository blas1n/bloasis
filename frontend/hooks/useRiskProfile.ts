"use client";

import { useState, useCallback, useEffect } from "react";
import { api } from "@/lib/api";
import type { UserPreferences, RiskProfile } from "@/lib/types";

export function useRiskProfile(userId: string) {
  const [preferences, setPreferences] = useState<UserPreferences | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPreferences = useCallback(async () => {
    setIsLoading(true);
    const { data, error: apiError } = await api.getUserPreferences(userId);

    if (apiError) {
      setError(apiError);
    } else if (data) {
      setPreferences(data);
    }

    setIsLoading(false);
  }, [userId]);

  const updateRiskProfile = useCallback(
    async (riskProfile: RiskProfile) => {
      setIsLoading(true);
      const { data, error: apiError } = await api.updateRiskProfile(userId, riskProfile);

      if (apiError) {
        setError(apiError);
      } else if (data) {
        setPreferences(data);
      }

      setIsLoading(false);
    },
    [userId]
  );

  useEffect(() => {
    fetchPreferences();
  }, [fetchPreferences]);

  return {
    riskProfile: preferences?.riskProfile || "moderate",
    isLoading,
    error,
    updateRiskProfile,
  };
}
