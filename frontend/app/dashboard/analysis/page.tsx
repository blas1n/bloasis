"use client";

import { MarketRegime } from "@/components/dashboard/MarketRegime";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

type Sentiment = "bullish" | "bearish" | "neutral";

interface Sector {
  name: string;
  weight: number;
  sentiment: Sentiment;
}

export default function AnalysisPage() {
  // Mock sector data - would come from API
  const sectors: Sector[] = [
    { name: "Technology", weight: 25, sentiment: "bullish" },
    { name: "Healthcare", weight: 20, sentiment: "neutral" },
    { name: "Financials", weight: 15, sentiment: "bullish" },
    { name: "Consumer Discretionary", weight: 15, sentiment: "bearish" },
    { name: "Energy", weight: 10, sentiment: "neutral" },
    { name: "Utilities", weight: 10, sentiment: "neutral" },
    { name: "Other", weight: 5, sentiment: "neutral" },
  ];

  const sentimentColors: Record<Sentiment, "success" | "danger" | "default"> = {
    bullish: "success",
    bearish: "danger",
    neutral: "default",
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Market Analysis</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Market Regime */}
        <section>
          <MarketRegime />
        </section>

        {/* AI Analysis */}
        <section>
          <Card>
            <h3 className="text-lg font-semibold mb-4">AI Analysis Summary</h3>
            <div className="space-y-4">
              <div>
                <p className="text-sm text-gray-500">Market Outlook</p>
                <p className="text-gray-900">
                  Current market conditions suggest a cautiously optimistic
                  stance. Key indicators show mixed signals with VIX at moderate
                  levels.
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Recommended Strategy</p>
                <p className="text-gray-900">
                  Focus on quality growth stocks with strong fundamentals.
                  Maintain defensive positions in utilities and healthcare.
                </p>
              </div>
            </div>
          </Card>
        </section>
      </div>

      {/* Sector Analysis */}
      <section>
        <Card>
          <h3 className="text-lg font-semibold mb-4">Sector Allocation</h3>
          <div className="space-y-3">
            {sectors.map((sector) => (
              <div
                key={sector.name}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium text-gray-900">
                    {sector.name}
                  </span>
                  <Badge variant={sentimentColors[sector.sentiment]}>
                    {sector.sentiment}
                  </Badge>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-32 bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-primary-600 h-2 rounded-full"
                      style={{ width: `${sector.weight}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium text-gray-600 w-12 text-right">
                    {sector.weight}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </section>
    </div>
  );
}
