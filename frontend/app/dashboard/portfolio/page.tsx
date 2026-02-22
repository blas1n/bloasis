"use client";

import { PortfolioSummary } from "@/components/dashboard/PortfolioSummary";
import { PositionsList } from "@/components/dashboard/PositionsList";
import { usePortfolio } from "@/hooks/usePortfolio";

export default function PortfolioPage() {
  const userId = "00000000-0000-0000-0000-000000000001";
  const { summary, positions, isLoading, error, refetch } = usePortfolio(userId);

  return (
    <div className="p-8 space-y-8">
      <h1 className="text-2xl font-bold text-text-primary">Portfolio</h1>

      <PortfolioSummary summary={summary} isLoading={isLoading} error={error} onRetry={refetch} variant="portfolio" />
      <PositionsList positions={positions} isLoading={isLoading} error={error} onRetry={refetch} />
    </div>
  );
}
