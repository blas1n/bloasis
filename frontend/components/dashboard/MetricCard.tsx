"use client";

export interface MetricCardProps {
  label: string;
  value: string;
  trend?: "up" | "down" | "neutral";
  icon?: string;
}

export function MetricCard({ label, value, trend = "neutral", icon }: MetricCardProps) {
  const trendColors = {
    up: "text-green-500",
    down: "text-red-500",
    neutral: "text-slate-300",
  };

  const trendIcons = {
    up: "↗",
    down: "↘",
    neutral: "→",
  };

  return (
    <div className="bg-slate-800 p-4 rounded-lg border border-slate-700">
      <div className="flex items-center gap-2 mb-1">
        {icon && <span className="text-lg">{icon}</span>}
        <p className="text-sm text-slate-400">{label}</p>
      </div>
      <p className={`text-2xl font-bold ${trendColors[trend]}`}>
        {trendIcons[trend]} {value}
      </p>
    </div>
  );
}
