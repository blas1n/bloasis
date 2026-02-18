"use client";

import { useTradeHistory } from "@/hooks/useTradeHistory";

export function TradingLog({ userId }: { userId: string }) {
  const { trades, isLoading, error } = useTradeHistory(userId, 20);

  if (error) {
    return (
      <div className="bg-slate-800 p-6 rounded-lg border border-red-500">
        <p className="text-red-500">Error loading trades: {error}</p>
      </div>
    );
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatDateTime = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
      <h3 className="text-lg font-semibold text-white mb-4">📜 Trading History</h3>

      {isLoading && trades.length === 0 ? (
        <div className="text-center py-8 text-slate-400">Loading...</div>
      ) : trades.length === 0 ? (
        <div className="text-center py-8 text-slate-400">No trades yet</div>
      ) : (
        <div className="space-y-3 max-h-[600px] overflow-y-auto">
          {trades.map((trade) => (
            <div
              key={trade.orderId}
              className="p-4 bg-slate-700 rounded border border-slate-600 hover:border-blue-500 transition-colors"
            >
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-white font-semibold">
                    <span
                      className={
                        trade.side === "buy"
                          ? "text-green-500"
                          : "text-red-500"
                      }
                    >
                      {trade.side.toUpperCase()}
                    </span>{" "}
                    {trade.symbol} × {trade.qty}
                  </p>
                  <p className="text-sm text-slate-400">
                    {formatDateTime(trade.executedAt)}
                  </p>
                </div>

                <div className="text-right">
                  <p className="text-white font-mono">
                    {formatCurrency(trade.price)}
                  </p>
                  <span className="px-2 py-1 bg-green-500 text-slate-900 text-xs rounded font-semibold">
                    EXECUTED
                  </span>
                </div>
              </div>

              {/* AI Reason */}
              {trade.aiReason && (
                <div className="mt-3 p-3 bg-slate-800 rounded border border-blue-500">
                  <p className="text-xs text-blue-400 font-semibold mb-1">
                    🤖 AI Reasoning:
                  </p>
                  <p className="text-sm text-slate-300">{trade.aiReason}</p>
                </div>
              )}

              {/* Realized P&L (for sell trades) */}
              {trade.side === "sell" && trade.realizedPnl !== 0 && (
                <div className="mt-2 text-sm">
                  <span className="text-slate-400">Realized P&L: </span>
                  <span
                    className={
                      trade.realizedPnl > 0
                        ? "text-green-500"
                        : "text-red-500"
                    }
                  >
                    {formatCurrency(trade.realizedPnl)}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
