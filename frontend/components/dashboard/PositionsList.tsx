"use client";

import { usePortfolio } from "@/hooks/usePortfolio";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { formatCurrency, formatPercent } from "@/lib/formatters";

interface PositionsListProps {
  userId: string;
}

export function PositionsList({ userId }: PositionsListProps) {
  const { positions, isLoading, error, refetch } = usePortfolio(userId);

  if (isLoading) {
    return (
      <Card>
        <LoadingSpinner />
      </Card>
    );
  }

  if (error) {
    return <ErrorMessage error={error} onRetry={refetch} />;
  }

  if (!positions || positions.length === 0) {
    return (
      <Card>
        <h3 className="text-lg font-semibold mb-4">Positions</h3>
        <p className="text-gray-500 text-center py-8">No open positions</p>
      </Card>
    );
  }

  return (
    <Card>
      <h3 className="text-lg font-semibold mb-4">Positions</h3>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead>
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Symbol
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Qty
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Avg Cost
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Value
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                P&amp;L
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {positions.map((position) => (
              <tr key={position.symbol} className="hover:bg-gray-50">
                <td className="px-4 py-3 whitespace-nowrap">
                  <span className="font-medium text-gray-900">
                    {position.symbol}
                  </span>
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-gray-600">
                  {position.quantity}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-gray-600">
                  {formatCurrency(position.avgCost)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-gray-600">
                  {formatCurrency(position.currentPrice)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-gray-900 font-medium">
                  {formatCurrency(position.currentValue)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right">
                  <div
                    className={
                      position.unrealizedPnl >= 0
                        ? "text-green-600"
                        : "text-red-600"
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
