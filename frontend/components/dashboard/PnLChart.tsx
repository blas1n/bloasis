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
        <h3 className="text-lg font-semibold text-text-primary mb-4">P&amp;L History</h3>
        <div className="h-64 bg-bg-surface rounded animate-pulse" />
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card>
        <h3 className="text-lg font-semibold text-text-primary mb-4">P&amp;L History</h3>
        <div className="h-64 flex items-center justify-center text-text-secondary">
          No P&amp;L data available
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <h3 className="text-lg font-semibold text-text-primary mb-4">P&amp;L History</h3>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#2D3748" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: "#6B7789" }}
              tickLine={false}
              axisLine={{ stroke: "#2D3748" }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "#6B7789" }}
              tickLine={false}
              axisLine={{ stroke: "#2D3748" }}
              tickFormatter={(value) => `$${value.toLocaleString()}`}
            />
            <Tooltip
              formatter={(value: number) => [
                `$${value.toLocaleString()}`,
                "P&L",
              ]}
              labelStyle={{ color: "#B8C5D0" }}
              contentStyle={{
                backgroundColor: "#1A2332",
                border: "1px solid #2D3748",
                borderRadius: "0.5rem",
              }}
              itemStyle={{ color: "#00D9FF" }}
            />
            <Line
              type="monotone"
              dataKey="pnl"
              stroke="#00D9FF"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: "#00D9FF" }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
