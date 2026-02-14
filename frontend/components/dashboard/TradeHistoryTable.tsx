import { Trade } from "@/lib/types";
import { Card, LoadingSpinner, ErrorMessage, Badge } from "@/components/ui";
import { formatCurrency, formatDateTime } from "@/lib/formatters";

interface TradeHistoryTableProps {
  trades: Trade[];
  isLoading: boolean;
  error: string | null;
}

export function TradeHistoryTable({
  trades,
  isLoading,
  error,
}: TradeHistoryTableProps) {
  if (isLoading) {
    return (
      <Card title="Trade History">
        <div className="flex justify-center py-8">
          <LoadingSpinner size="md" />
        </div>
      </Card>
    );
  }

  if (error) {
    return <ErrorMessage message={error} />;
  }

  if (trades.length === 0) {
    return (
      <Card title="Trade History">
        <p className="text-center text-text-secondary py-8">No trades yet</p>
      </Card>
    );
  }

  return (
    <Card title="Trade History">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-border-custom">
          <thead>
            <tr className="text-left text-xs font-medium text-text-secondary uppercase">
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3">Quantity</th>
              <th className="px-4 py-3">Price</th>
              <th className="px-4 py-3">Commission</th>
              <th className="px-4 py-3">Executed At</th>
              <th className="px-4 py-3 text-right">P&L</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-custom">
            {trades.map((trade) => (
              <tr key={trade.trade_id} className="text-sm">
                <td className="px-4 py-3 font-medium text-text-primary">
                  {trade.symbol}
                </td>
                <td className="px-4 py-3">
                  <Badge variant={trade.side === "BUY" ? "success" : "danger"}>
                    {trade.side}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-text-primary">
                  {trade.quantity}
                </td>
                <td className="px-4 py-3 text-text-primary">
                  {formatCurrency(trade.price)}
                </td>
                <td className="px-4 py-3 text-text-secondary">
                  {formatCurrency(trade.commission)}
                </td>
                <td className="px-4 py-3 text-text-secondary">
                  {formatDateTime(trade.executed_at)}
                </td>
                <td className="px-4 py-3 text-right">
                  {trade.realized_pnl !== null && (
                    <span
                      className={
                        trade.realized_pnl >= 0
                          ? "text-green-600 dark:text-green-400"
                          : "text-red-600 dark:text-red-400"
                      }
                    >
                      {formatCurrency(trade.realized_pnl)}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
