"use client";

import { PortfolioSummary } from "@/components/dashboard/PortfolioSummary";
import { PositionsList } from "@/components/dashboard/PositionsList";

export default function PortfolioPage() {
  const userId = "00000000-0000-0000-0000-000000000001";

  return (
    <div className="p-8 space-y-8">
      <PortfolioSummary userId={userId} variant="portfolio" />
      <PositionsList userId={userId} />
    </div>
  );
}
