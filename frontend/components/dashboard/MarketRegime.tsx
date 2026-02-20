"use client";

import { useMarketRegime } from "@/hooks/useMarketRegime";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import type { RegimeType } from "@/lib/types";

const regimeLabels: Record<RegimeType, string> = {
  risk_on: "BULL MARKET",
  risk_off: "BEAR MARKET",
  crisis: "CRISIS MODE",
  recovery: "RECOVERY",
};

const regimeTextColors: Record<RegimeType, string> = {
  risk_on: "text-theme-success",
  risk_off: "text-yellow-600 dark:text-yellow-400",
  crisis: "text-theme-danger",
  recovery: "text-theme-primary",
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
      <p className="text-sm font-semibold text-text-primary mb-3 tracking-wider">
        MARKET REGIME
      </p>

      <p className={`text-2xl font-bold mb-2 ${regimeTextColors[regime.regime]}`}>
        {regimeLabels[regime.regime]}
      </p>

      <p className="text-sm text-text-secondary mb-4">
        Confidence: {(regime.confidence * 100).toFixed(0)}%
      </p>

      {regime.reasoning && (
        <div>
          <p className="text-xs font-semibold mb-1 text-theme-primary">
            AI Analysis:
          </p>
          <p className="text-sm text-text-secondary">{regime.reasoning}</p>
        </div>
      )}
    </Card>
  );
}
