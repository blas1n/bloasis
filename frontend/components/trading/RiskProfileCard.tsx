"use client";

import { useRiskProfile } from "@/hooks/useRiskProfile";
import { Card } from "@/components/ui/Card";
import type { RiskProfile } from "@/lib/types";

export function RiskProfileCard({ userId }: { userId: string }) {
  const { riskProfile, isLoading, error, updateRiskProfile } = useRiskProfile(userId);

  const profiles: Array<{
    id: RiskProfile;
    icon: string;
    label: string;
  }> = [
    {
      id: "conservative",
      icon: "🛡️",
      label: "Conservative - Low Risk",
    },
    {
      id: "moderate",
      icon: "⚖️",
      label: "Moderate - Balanced",
    },
    {
      id: "aggressive",
      icon: "🚀",
      label: "Aggressive - High Risk",
    },
  ];

  return (
    <Card>
      <h3 className="text-lg font-bold text-text-primary mb-1">Risk Profile</h3>
      <p className="text-sm text-text-muted mb-5">Select your investment risk tolerance</p>

      {error && (
        <p className="mb-3 text-xs text-red-400">{error}</p>
      )}

      <div className="space-y-3">
        {profiles.map((profile) => {
          const isSelected = riskProfile === profile.id;

          return (
            <button
              key={profile.id}
              onClick={() => updateRiskProfile(profile.id)}
              disabled={isLoading}
              className={`w-full p-4 rounded-lg border text-left transition-all disabled:opacity-50 ${
                isSelected
                  ? "border-2 border-theme-primary bg-bg-nav-active"
                  : "bg-bg-surface border-border-custom hover:border-theme-primary"
              }`}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{profile.icon}</span>
                <div
                  className={`font-semibold ${isSelected ? "text-theme-primary" : "text-text-primary"}`}
                >
                  {profile.label}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </Card>
  );
}
