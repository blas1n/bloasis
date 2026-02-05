"use client";

import { useMarketRegime } from "@/hooks/useMarketRegime";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import type { RegimeType, RiskLevel } from "@/lib/types";

const regimeColors: Record<RegimeType, string> = {
  risk_on: "bg-green-100 text-green-800",
  risk_off: "bg-yellow-100 text-yellow-800",
  crisis: "bg-red-100 text-red-800",
  recovery: "bg-blue-100 text-blue-800",
};

const regimeLabels: Record<RegimeType, string> = {
  risk_on: "RISK ON",
  risk_off: "RISK OFF",
  crisis: "CRISIS",
  recovery: "RECOVERY",
};

const riskLevelVariant: Record<RiskLevel, "success" | "warning" | "danger"> = {
  low: "success",
  medium: "warning",
  high: "danger",
};

export function MarketRegime() {
  const { regime, isLoading, error, refetch } = useMarketRegime();

  if (isLoading) {
    return (
      <Card>
        <LoadingSpinner />
      </Card>
    );
  }

  if (error) {
    return <ErrorMessage error={error} onRetry={refetch} />;
  }

  if (!regime) {
    return null;
  }

  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Market Regime</h3>
          <span
            className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium mt-2 ${
              regimeColors[regime.regime]
            }`}
          >
            {regimeLabels[regime.regime]}
          </span>
        </div>
        <div className="text-right">
          <p className="text-sm text-gray-500">Confidence</p>
          <p className="text-xl font-bold text-gray-900">
            {(regime.confidence * 100).toFixed(0)}%
          </p>
        </div>
      </div>

      <div className="mt-4">
        <p className="text-sm text-gray-600">{regime.reasoning}</p>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-gray-500">VIX</p>
          <p className="font-medium text-gray-900">
            {regime.indicators?.vix?.toFixed(1) ?? "N/A"}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500">Risk Level</p>
          <Badge variant={riskLevelVariant[regime.riskLevel]}>
            {regime.riskLevel.toUpperCase()}
          </Badge>
        </div>
      </div>
    </Card>
  );
}
