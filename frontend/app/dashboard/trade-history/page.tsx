"use client";

import { useTradeHistory } from "@/hooks/useTradeHistory";
import { TradeHistoryTable } from "@/components/dashboard";
import { Card } from "@/components/ui";
import { formatCurrency } from "@/lib/formatters";

export default function TradeHistoryPage() {
  const userId = "demo-user"; // In production, get from auth context
  const { trades, isLoading, error } = useTradeHistory(userId);

  // Calculate total realized P&L
  const totalPnL = trades.reduce(
    (sum, trade) => sum + (trade.realized_pnl || 0),
    0
  );

  // Calculate win rate
  const winningTrades = trades.filter(
    (t) => (t.realized_pnl || 0) > 0
  ).length;
  const winRate = trades.length > 0 ? (winningTrades / trades.length) * 100 : 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-text-primary">Trade History</h1>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <div className="space-y-1">
            <p className="text-sm text-text-secondary">Total Trades</p>
            <p className="text-2xl font-bold text-text-primary">
              {trades.length}
            </p>
          </div>
        </Card>
        <Card>
          <div className="space-y-1">
            <p className="text-sm text-text-secondary">Realized P&L</p>
            <p
              className={`text-2xl font-bold ${
                totalPnL >= 0
                  ? "text-green-600 dark:text-green-400"
                  : "text-red-600 dark:text-red-400"
              }`}
            >
              {formatCurrency(totalPnL)}
            </p>
          </div>
        </Card>
        <Card>
          <div className="space-y-1">
            <p className="text-sm text-text-secondary">Win Rate</p>
            <p className="text-2xl font-bold text-text-primary">
              {trades.length > 0 ? `${winRate.toFixed(1)}%` : "N/A"}
            </p>
          </div>
        </Card>
      </div>

      {/* Trade History Table */}
      <TradeHistoryTable trades={trades} isLoading={isLoading} error={error} />
    </div>
  );
}
