"use client";

import { AITradingControl } from "@/components/trading/AITradingControl";
import { RiskProfileCard } from "@/components/trading/RiskProfileCard";
import { TradingLog } from "@/components/trading/TradingLog";
import { useAuth } from "@/lib/auth-context";

export default function TradingPage() {
  const { user } = useAuth();
  const userId = user?.userId ?? "";

  return (
    <div className="p-8 space-y-8">
      {/* Row 1: AI Trading Control + Risk Profile */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-6">
        <AITradingControl userId={userId} />
        <RiskProfileCard userId={userId} />
      </div>

      {/* Row 2: Trading Log */}
      <TradingLog userId={userId} />
    </div>
  );
}
