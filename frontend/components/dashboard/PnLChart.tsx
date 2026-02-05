"use client";

import { Card } from "@/components/ui/Card";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface PnLDataPoint {
  date: string;
  pnl: number;
  equity: number;
}

interface PnLChartProps {
  data: PnLDataPoint[];
  isLoading?: boolean;
}

export function PnLChart({ data, isLoading }: PnLChartProps) {
  if (isLoading) {
    return (
      <Card>
        <h3 className="text-lg font-semibold mb-4">P&amp;L History</h3>
        <div className="h-64 bg-gray-100 rounded animate-pulse" />
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card>
        <h3 className="text-lg font-semibold mb-4">P&amp;L History</h3>
        <div className="h-64 flex items-center justify-center text-gray-500">
          No P&amp;L data available
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <h3 className="text-lg font-semibold mb-4">P&amp;L History</h3>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={{ stroke: "#e5e7eb" }}
              tickFormatter={(value) => `$${value.toLocaleString()}`}
            />
            <Tooltip
              formatter={(value: number) => [
                `$${value.toLocaleString()}`,
                "P&L",
              ]}
              labelStyle={{ color: "#374151" }}
              contentStyle={{
                backgroundColor: "white",
                border: "1px solid #e5e7eb",
                borderRadius: "0.5rem",
              }}
            />
            <Line
              type="monotone"
              dataKey="pnl"
              stroke="#0ea5e9"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
