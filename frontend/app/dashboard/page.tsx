"use client";

import { PortfolioSummary } from "@/components/dashboard/PortfolioSummary";
import { MarketRegime } from "@/components/dashboard/MarketRegime";
import { AITradingControl } from "@/components/trading/AITradingControl";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { usePortfolio } from "@/hooks/usePortfolio";
import { formatCurrency, formatPercent } from "@/lib/formatters";

export default function DashboardPage() {
  const userId = "demo-user";
  const { summary } = usePortfolio(userId);

  return (
    <div className="p-8 space-y-8">
      {/* Row 1: Market Regime + Portfolio Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-[480px_1fr] gap-6">
        <MarketRegime />
        <PortfolioSummary userId={userId} variant="dashboard" />
      </div>

      {/* Row 2: AI Trading Control */}
      <AITradingControl userId={userId} />

      {/* Row 3: Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <MetricCard
          label="Daily P&L"
          value={summary ? `${formatCurrency(summary.dailyPnl)} (${formatPercent(summary.dailyPnlPct)})` : "—"}
          trend={summary && summary.dailyPnl >= 0 ? "up" : "down"}
        />
        <MetricCard
          label="Unrealized P&L"
          value={summary ? formatCurrency(summary.unrealizedPnl) : "—"}
          trend={summary && summary.unrealizedPnl >= 0 ? "up" : "down"}
        />
        <MetricCard
          label="Buying Power"
          value={summary ? formatCurrency(summary.buyingPower) : "—"}
          trend="neutral"
        />
      </div>
    </div>
  );
}
