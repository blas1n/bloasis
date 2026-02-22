"use client";

import { usePortfolio } from "@/hooks/usePortfolio";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { formatCurrency, formatPercent } from "@/lib/formatters";
import type { Position } from "@/lib/types";

interface PositionsListProps {
  userId?: string;
  /** When provided, the component uses these props instead of fetching via hook. */
  positions?: Position[];
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function PositionsList({
  userId,
  positions: propsPositions,
  isLoading: propsIsLoading,
  error: propsError,
  onRetry: propsOnRetry,
}: PositionsListProps) {
  // Always call the hook (Rules of Hooks), but skip fetch when props are provided
  const hook = usePortfolio(propsPositions !== undefined ? "" : userId || "");

  const positions = propsPositions !== undefined ? propsPositions : hook.positions;
  const isLoading = propsIsLoading !== undefined ? propsIsLoading : hook.isLoading;
  const error = propsError !== undefined ? propsError : hook.error;
  const onRetry = propsOnRetry || hook.refetch;

  if (isLoading) {
    return (
      <Card>
        <LoadingSpinner />
      </Card>
    );
  }

  if (error) {
    return <ErrorMessage error={error} onRetry={onRetry} />;
  }

  if (!positions || positions.length === 0) {
    return (
      <Card>
        <h3 className="text-lg font-semibold text-text-primary mb-4">Positions (0 Holdings)</h3>
        <p className="text-text-secondary text-center py-8">No open positions</p>
      </Card>
    );
  }

  return (
    <Card>
      <h3 className="text-lg font-semibold text-text-primary mb-4">Positions ({positions.length} Holdings)</h3>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-border-custom">
          <thead>
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-text-secondary uppercase tracking-wider">
                Symbol
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-text-secondary uppercase tracking-wider">
                Qty
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-text-secondary uppercase tracking-wider">
                Avg Cost
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-text-secondary uppercase tracking-wider">
                Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-text-secondary uppercase tracking-wider">
                Value
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-text-secondary uppercase tracking-wider">
                P&amp;L
              </th>
            </tr>
          </thead>
          <tbody className="bg-bg-elevated divide-y divide-border-custom">
            {positions.map((position) => (
              <tr key={position.symbol} className="hover:bg-bg-surface">
                <td className="px-4 py-3 whitespace-nowrap">
                  <span className="font-medium text-text-primary">
                    {position.symbol}
                  </span>
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-text-secondary">
                  {position.quantity}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-text-secondary">
                  {formatCurrency(position.avgCost)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-text-secondary">
                  {formatCurrency(position.currentPrice)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-text-primary font-medium">
                  {formatCurrency(position.currentValue)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right">
                  <div
                    className={
                      position.unrealizedPnl >= 0
                        ? "text-theme-success"
                        : "text-theme-danger"
                    }
                  >
                    <span className="font-medium">
                      {formatCurrency(position.unrealizedPnl)}
                    </span>
                    <Badge
                      variant={
                        position.unrealizedPnlPercent >= 0 ? "success" : "danger"
                      }
                      className="ml-2"
                    >
                      {formatPercent(position.unrealizedPnlPercent)}
                    </Badge>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
