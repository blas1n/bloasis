"use client";

import { PortfolioSummary } from "@/components/dashboard/PortfolioSummary";
import { MarketRegime } from "@/components/dashboard/MarketRegime";
import { PositionsList } from "@/components/dashboard/PositionsList";
import { SignalsList } from "@/components/dashboard/SignalsList";
import { useSignals } from "@/hooks/useSignals";

export default function DashboardPage() {
  // In production, get from auth context
  const userId = "demo-user";
  const { signals, isLoading: signalsLoading } = useSignals(userId);

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      {/* Portfolio Summary */}
      <section>
        <PortfolioSummary userId={userId} />
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Market Regime */}
        <section className="lg:col-span-1">
          <MarketRegime />
        </section>

        {/* Positions */}
        <section className="lg:col-span-2">
          <PositionsList userId={userId} />
        </section>
      </div>

      {/* Trading Signals */}
      <section>
        <SignalsList signals={signals} isLoading={signalsLoading} />
      </section>
    </div>
  );
}
