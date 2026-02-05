"use client";

import { SignalsList } from "@/components/dashboard/SignalsList";
import { MarketRegime } from "@/components/dashboard/MarketRegime";
import { Card } from "@/components/ui/Card";
import { useSignals } from "@/hooks/useSignals";

export default function SignalsPage() {
  // In production, get from auth context
  const userId = "demo-user";
  const { signals, isLoading, error, refetch } = useSignals(userId);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Trading Signals</h1>
        <button
          onClick={refetch}
          className="px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 transition-colors"
        >
          Refresh Signals
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Market Context */}
        <section className="lg:col-span-1">
          <MarketRegime />
        </section>

        {/* Signal Stats */}
        <section className="lg:col-span-2">
          <Card>
            <h3 className="text-lg font-semibold mb-4">Signal Summary</h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <p className="text-3xl font-bold text-green-600">
                  {signals.filter((s) => s.action === "buy").length}
                </p>
                <p className="text-sm text-gray-500">Buy Signals</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-bold text-red-600">
                  {signals.filter((s) => s.action === "sell").length}
                </p>
                <p className="text-sm text-gray-500">Sell Signals</p>
              </div>
              <div className="text-center">
                <p className="text-3xl font-bold text-gray-600">
                  {signals.filter((s) => s.action === "hold").length}
                </p>
                <p className="text-sm text-gray-500">Hold Signals</p>
              </div>
            </div>
          </Card>
        </section>
      </div>

      {/* Signals List */}
      <section>
        <SignalsList signals={signals} isLoading={isLoading} />
      </section>
    </div>
  );
}
