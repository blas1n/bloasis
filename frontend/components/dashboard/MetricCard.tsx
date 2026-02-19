"use client";

export interface MetricCardProps {
  label: string;
  value: string;
  trend?: "up" | "down" | "neutral";
}

export function MetricCard({ label, value, trend = "neutral" }: MetricCardProps) {
  const trendColors = {
    up: "text-theme-success",
    down: "text-theme-danger",
    neutral: "text-text-secondary",
  };

  return (
    <div className="bg-bg-elevated p-6 rounded-xl border border-border-custom">
      <p className="text-sm text-text-muted mb-2">{label}</p>
      <p className={`text-2xl font-bold font-mono ${trendColors[trend]}`}>
        {value}
      </p>
    </div>
  );
}
