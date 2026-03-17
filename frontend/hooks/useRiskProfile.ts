"use client";

import { useState, useCallback, useEffect } from "react";
import client from "@/lib/api-client";
import type { UserPreferences, RiskProfile } from "@/lib/api-types";

export function useRiskProfile(userId: string) {
  const [preferences, setPreferences] = useState<UserPreferences | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPreferences = useCallback(async () => {
    setIsLoading(true);
    const { data, error: apiError } = await client.GET(
      "/v1/users/{user_id}/preferences",
      {
        params: { path: { user_id: userId } },
      }
    );

    if (apiError) {
      setError("Failed to load preferences");
    } else if (data) {
      // Runtime data is camelCase (CamelJSONResponse), cast accordingly
      setPreferences(data as unknown as UserPreferences);
    }

    setIsLoading(false);
  }, [userId]);

  const updateRiskProfile = useCallback(
    async (riskProfile: RiskProfile) => {
      if (!preferences) return;
      setIsLoading(true);
      const { data, error: apiError } = await client.PATCH(
        "/v1/users/{user_id}/preferences",
        {
          params: { path: { user_id: userId } },
          body: { riskProfile },
        }
      );

      if (apiError) {
        setError("Failed to update risk profile");
      } else if (data) {
        // Runtime data is camelCase (CamelJSONResponse), cast accordingly
        setPreferences(data as unknown as UserPreferences);
      }

      setIsLoading(false);
    },
    [userId, preferences]
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
