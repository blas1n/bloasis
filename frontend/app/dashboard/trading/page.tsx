"use client";

import { AITradingControl } from "@/components/trading/AITradingControl";
import { RiskProfileCard } from "@/components/trading/RiskProfileCard";
import { TradingLog } from "@/components/trading/TradingLog";

export default function TradingPage() {
  const userId = "demo-user"; // TODO: Get from auth context

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">⚡ Trading Management</h1>
        <p className="text-slate-400 mt-1">
          Control AI auto-trading and manage your investment profile
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column */}
        <div className="space-y-6">
          <AITradingControl userId={userId} />
          <RiskProfileCard userId={userId} />
        </div>

        {/* Right Column */}
        <TradingLog userId={userId} />
      </div>
    </div>
  );
}
