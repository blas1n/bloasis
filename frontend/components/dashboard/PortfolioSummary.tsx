"use client";

import { usePortfolio } from "@/hooks/usePortfolio";
import { Card } from "@/components/ui/Card";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { formatCurrency, formatPercent } from "@/lib/formatters";
import type { PortfolioSummary as PortfolioSummaryType } from "@/lib/types";

interface PortfolioSummaryProps {
  userId?: string;
  variant?: "dashboard" | "portfolio";
  /** When provided, the component uses these props instead of fetching via hook. */
  summary?: PortfolioSummaryType | null;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function PortfolioSummary({
  userId,
  variant = "portfolio",
  summary: propsSummary,
  isLoading: propsIsLoading,
  error: propsError,
  onRetry: propsOnRetry,
}: PortfolioSummaryProps) {
  // Always call the hook (Rules of Hooks), but skip fetch when props are provided
  const hook = usePortfolio(propsSummary !== undefined ? "" : userId || "");

  const summary = propsSummary !== undefined ? propsSummary : hook.summary;
  const isLoading = propsIsLoading !== undefined ? propsIsLoading : hook.isLoading;
  const error = propsError !== undefined ? propsError : hook.error;
  const onRetry = propsOnRetry || hook.refetch;

  if (isLoading) {
    return (
      <Card className="animate-pulse">
        <div className="h-4 bg-bg-surface rounded w-36 mb-4" />
        <div className="h-8 bg-bg-surface rounded w-48 mb-3" />
        <div className="h-5 bg-bg-surface rounded w-32" />
      </Card>
    );
  }

  if (error) {
    return <ErrorMessage error={error} onRetry={onRetry} />;
  }

  if (!summary) {
    return null;
  }

  // Dashboard variant: PORTFOLIO SUMMARY — Total Value + Daily P&L (간결)
  if (variant === "dashboard") {
    return (
      <Card>
        <p className="text-sm font-semibold text-text-primary mb-4 tracking-wider">
          PORTFOLIO SUMMARY
        </p>
        <p className="text-3xl font-bold font-mono text-text-primary mb-2">
          {formatCurrency(summary.totalEquity)}
        </p>
        <div>
          <p className="text-xs text-text-muted mb-1">Daily P&amp;L</p>
          <p className={`text-lg font-bold font-mono ${summary.dailyPnl >= 0 ? "text-theme-success" : "text-theme-danger"}`}>
            {formatCurrency(summary.dailyPnl)}
            <span className="text-sm font-normal ml-2">
              ({formatPercent(summary.dailyPnlPct)})
            </span>
          </p>
        </div>
      </Card>
    );
  }

  // Portfolio variant: Portfolio Overview — Total Value, Total P&L, Cash (가로 배치)
  return (
    <Card>
      <h3 className="text-lg font-semibold text-text-primary mb-5">Portfolio Overview</h3>
      <div className="flex flex-wrap gap-8">
        <div>
          <p className="text-xs text-text-muted mb-1">Total Value</p>
          <p className="text-2xl font-bold font-mono text-text-primary">
            {formatCurrency(summary.totalEquity)}
          </p>
        </div>
        <div>
          <p className="text-xs text-text-muted mb-1">Total P&amp;L</p>
          <p className={`text-2xl font-bold font-mono ${summary.unrealizedPnl >= 0 ? "text-theme-success" : "text-theme-danger"}`}>
            {formatCurrency(summary.unrealizedPnl)}
            <span className="text-sm font-normal ml-2">
              ({formatPercent(summary.unrealizedPnl / summary.totalEquity * 100)})
            </span>
          </p>
        </div>
        <div>
          <p className="text-xs text-text-muted mb-1">Cash</p>
          <p className="text-2xl font-bold font-mono text-text-secondary">
            {formatCurrency(summary.buyingPower)}
          </p>
        </div>
      </div>
    </Card>
  );
}
