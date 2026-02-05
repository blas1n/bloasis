"use client";

import { usePortfolio } from "@/hooks/usePortfolio";
import { Card } from "@/components/ui/Card";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { formatCurrency, formatPercent } from "@/lib/formatters";

interface PortfolioSummaryProps {
  userId: string;
}

export function PortfolioSummary({ userId }: PortfolioSummaryProps) {
  const { summary, isLoading, error, refetch } = usePortfolio(userId);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i} className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-24 mb-2" />
            <div className="h-8 bg-gray-200 rounded w-32" />
          </Card>
        ))}
      </div>
    );
  }

  if (error) {
    return <ErrorMessage error={error} onRetry={refetch} />;
  }

  if (!summary) {
    return null;
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <Card>
        <h3 className="text-sm text-gray-500">Total Equity</h3>
        <p className="text-2xl font-bold text-gray-900">
          {formatCurrency(summary.totalEquity)}
        </p>
      </Card>

      <Card>
        <h3 className="text-sm text-gray-500">Today&apos;s P&amp;L</h3>
        <p
          className={`text-2xl font-bold ${
            summary.dailyPnl >= 0 ? "text-green-600" : "text-red-600"
          }`}
        >
          {formatCurrency(summary.dailyPnl)}
          <span className="text-sm ml-1">
            ({formatPercent(summary.dailyPnlPct)})
          </span>
        </p>
      </Card>

      <Card>
        <h3 className="text-sm text-gray-500">Unrealized P&amp;L</h3>
        <p
          className={`text-2xl font-bold ${
            summary.unrealizedPnl >= 0 ? "text-green-600" : "text-red-600"
          }`}
        >
          {formatCurrency(summary.unrealizedPnl)}
        </p>
      </Card>

      <Card>
        <h3 className="text-sm text-gray-500">Buying Power</h3>
        <p className="text-2xl font-bold text-gray-900">
          {formatCurrency(summary.buyingPower)}
        </p>
      </Card>
    </div>
  );
}
