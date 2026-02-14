"use client";

import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { Signal } from "@/lib/types";

interface SignalsListProps {
  signals: Signal[];
  isLoading?: boolean;
}

const actionColors = {
  buy: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  sell: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  hold: "bg-gray-100 text-gray-800 dark:bg-bg-elevated dark:text-text-secondary",
};

export function SignalsList({ signals, isLoading }: SignalsListProps) {
  if (isLoading) {
    return (
      <Card>
        <h3 className="text-lg font-semibold mb-4">Trading Signals</h3>
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="flex items-center justify-between p-3 bg-bg-surface rounded-lg animate-pulse"
            >
              <div className="space-y-2">
                <div className="h-4 bg-bg-elevated rounded w-20" />
                <div className="h-3 bg-bg-elevated rounded w-40" />
              </div>
              <div className="h-8 bg-bg-elevated rounded w-16" />
            </div>
          ))}
        </div>
      </Card>
    );
  }

  if (signals.length === 0) {
    return (
      <Card>
        <h3 className="text-lg font-semibold mb-4">Trading Signals</h3>
        <p className="text-text-secondary text-center py-8">
          No trading signals available
        </p>
      </Card>
    );
  }

  return (
    <Card>
      <h3 className="text-lg font-semibold mb-4">Trading Signals</h3>

      <div className="space-y-3">
        {signals.map((signal) => (
          <div
            key={signal.symbol}
            className="flex items-center justify-between p-3 bg-bg-surface rounded-lg"
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-text-primary">{signal.symbol}</span>
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                    actionColors[signal.action]
                  }`}
                >
                  {signal.action.toUpperCase()}
                </span>
              </div>
              <p className="text-sm text-text-secondary mt-1">{signal.rationale}</p>
              <div className="flex gap-4 mt-2 text-xs text-text-secondary">
                <span>SL: ${signal.stopLoss.toFixed(2)}</span>
                <span>TP: ${signal.takeProfit.toFixed(2)}</span>
              </div>
            </div>

            <div className="text-right">
              <p className="text-sm font-medium text-text-primary">
                {(signal.confidence * 100).toFixed(0)}%
              </p>
              <p className="text-xs text-text-secondary">
                Size: {(signal.sizeRecommendation * 100).toFixed(1)}%
              </p>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
