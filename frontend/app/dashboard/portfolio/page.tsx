"use client";

import { PortfolioSummary } from "@/components/dashboard/PortfolioSummary";
import { PositionsList } from "@/components/dashboard/PositionsList";
import { PnLChart } from "@/components/dashboard/PnLChart";

export default function PortfolioPage() {
  // In production, get from auth context
  const userId = "demo-user";

  // Mock P&L data - would come from API
  const pnlData = [
    { date: "Mon", pnl: 1200, equity: 51200 },
    { date: "Tue", pnl: 1800, equity: 51800 },
    { date: "Wed", pnl: 1500, equity: 51500 },
    { date: "Thu", pnl: 2200, equity: 52200 },
    { date: "Fri", pnl: 2500, equity: 52500 },
  ];

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Portfolio</h1>

      {/* Portfolio Summary */}
      <section>
        <PortfolioSummary userId={userId} />
      </section>

      {/* P&L Chart */}
      <section>
        <PnLChart data={pnlData} />
      </section>

      {/* Positions */}
      <section>
        <PositionsList userId={userId} />
      </section>
    </div>
  );
}
