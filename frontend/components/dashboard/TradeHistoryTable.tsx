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
    return <ErrorMessage error={error} />;
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
              <tr key={trade.orderId} className="text-sm">
                <td className="px-4 py-3 font-medium text-text-primary">
                  {trade.symbol}
                </td>
                <td className="px-4 py-3">
                  <Badge variant={trade.side === "buy" ? "success" : "danger"}>
                    {trade.side.toUpperCase()}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-text-primary">
                  {trade.qty}
                </td>
                <td className="px-4 py-3 text-text-primary">
                  {formatCurrency(trade.price)}
                </td>
                <td className="px-4 py-3 text-text-secondary">
                  {formatCurrency(trade.commission)}
                </td>
                <td className="px-4 py-3 text-text-secondary">
                  {formatDateTime(trade.executedAt)}
                </td>
                <td className="px-4 py-3 text-right">
                  {trade.realizedPnl !== 0 && (
                    <span
                      className={
                        trade.realizedPnl >= 0
                          ? "text-green-600 dark:text-green-400"
                          : "text-red-600 dark:text-red-400"
                      }
                    >
                      {formatCurrency(trade.realizedPnl)}
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
