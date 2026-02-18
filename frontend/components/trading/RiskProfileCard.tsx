"use client";

import { useRiskProfile } from "@/hooks/useRiskProfile";
import type { RiskProfile } from "@/lib/types";

export function RiskProfileCard({ userId }: { userId: string }) {
  const { riskProfile, isLoading, updateRiskProfile } = useRiskProfile(userId);

  const profiles: Array<{
    id: RiskProfile;
    icon: string;
    label: string;
    description: string;
  }> = [
    {
      id: "conservative",
      icon: "🛡️",
      label: "Conservative",
      description: "Lower risk, steady returns",
    },
    {
      id: "moderate",
      icon: "⚖️",
      label: "Moderate",
      description: "Balanced risk and reward",
    },
    {
      id: "aggressive",
      icon: "🚀",
      label: "Aggressive",
      description: "Higher risk, higher potential",
    },
  ];

  return (
    <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
      <h3 className="text-lg font-semibold text-white mb-4">
        💼 Investment Profile
      </h3>

      <div className="space-y-3">
        {profiles.map((profile) => {
          const isSelected = riskProfile === profile.id;

          return (
            <button
              key={profile.id}
              onClick={() => updateRiskProfile(profile.id)}
              disabled={isLoading}
              className={`w-full p-4 rounded-lg border text-left transition-all ${
                isSelected
                  ? "bg-blue-900 bg-opacity-30 border-blue-500"
                  : "bg-slate-700 border-slate-600 hover:border-slate-500"
              } disabled:opacity-50`}
            >
              <div className="flex items-center gap-3">
                <span className="text-2xl">{profile.icon}</span>
                <div>
                  <div className="font-semibold text-white">{profile.label}</div>
                  <div className="text-sm text-slate-400">
                    {profile.description}
                  </div>
                </div>
                {isSelected && (
                  <span className="ml-auto text-blue-400">✓</span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
