"use client";

import { useTradeHistory } from "@/hooks/useTradeHistory";

export function TradingLog({ userId }: { userId: string }) {
  const { trades, isLoading, error } = useTradeHistory(userId, 20);

  if (error) {
    return (
      <div className="bg-bg-elevated p-6 rounded-lg border border-theme-danger">
        <p className="text-theme-danger">Error loading trades: {error}</p>
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
    <div className="bg-bg-elevated p-6 rounded-lg border border-border-custom">
      <h3 className="text-lg font-semibold text-text-primary mb-4">📜 Trading History</h3>

      {isLoading && trades.length === 0 ? (
        <div className="text-center py-8 text-text-muted">Loading...</div>
      ) : trades.length === 0 ? (
        <div className="text-center py-8 text-text-muted">No trades yet</div>
      ) : (
        <div className="space-y-3 max-h-[600px] overflow-y-auto">
          {trades.map((trade) => (
            <div
              key={trade.orderId}
              className="p-4 bg-bg-surface rounded border border-border-custom hover:border-theme-primary transition-colors"
            >
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-text-primary font-semibold">
                    <span
                      className={
                        trade.side === "buy"
                          ? "text-theme-success"
                          : "text-theme-danger"
                      }
                    >
                      {trade.side.toUpperCase()}
                    </span>{" "}
                    {trade.symbol} × {trade.qty}
                  </p>
                  <p className="text-sm text-text-muted">
                    {formatDateTime(trade.executedAt)}
                  </p>
                </div>

                <div className="text-right">
                  <p className="text-text-primary font-mono font-semibold">
                    {formatCurrency(trade.price)}
                  </p>
                  <span className="px-2 py-1 text-xs rounded font-semibold bg-theme-success/10 text-theme-success">
                    EXECUTED
                  </span>
                </div>
              </div>

              {/* AI Reason */}
              {trade.aiReason && (
                <div className="mt-3 p-3 bg-bg-elevated rounded border border-theme-primary">
                  <p className="text-xs font-semibold mb-1 text-theme-primary">
                    🤖 AI Reasoning:
                  </p>
                  <p className="text-sm text-text-secondary">{trade.aiReason}</p>
                </div>
              )}

              {/* Realized P&L (for sell trades) */}
              {trade.side === "sell" && trade.realizedPnl !== 0 && (
                <div className="mt-2 text-sm">
                  <span className="text-text-muted">Realized P&L: </span>
                  <span
                    className={
                      trade.realizedPnl > 0
                        ? "text-theme-success"
                        : "text-theme-danger"
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
