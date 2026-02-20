"use client";

import { useMarketRegime } from "@/hooks/useMarketRegime";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import type { RegimeType } from "@/lib/types";

const regimeLabels: Record<RegimeType, string> = {
  bull: "BULL MARKET",
  bear: "BEAR MARKET",
  sideways: "SIDEWAYS",
  crisis: "CRISIS MODE",
  recovery: "RECOVERY",
};

const regimeTextColors: Record<RegimeType, string> = {
  bull: "text-theme-success",
  bear: "text-yellow-600 dark:text-yellow-400",
  sideways: "text-text-secondary",
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
          <p className="text-xs font-semibold mb-2 text-theme-primary">
            AI Analysis:
          </p>
          <div className="text-sm text-text-secondary space-y-1">
            {regime.reasoning
              .split(/\. (?=[A-Z])/)
              .map((sentence, i, arr) => (
                <p key={i}>
                  {sentence}
                  {i < arr.length - 1 ? "." : ""}
                </p>
              ))}
          </div>
        </div>
      )}
    </Card>
  );
}
