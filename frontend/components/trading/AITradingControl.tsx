"use client";

import { useState, useEffect } from "react";
import { useTradingControl } from "@/hooks/useTradingControl";
import { api } from "@/lib/api";

export function AITradingControl({ userId }: { userId: string }) {
  const { status, isLoading, error, startTrading, stopTrading } =
    useTradingControl(userId);
  const [showStopDialog, setShowStopDialog] = useState(false);
  const [brokerConfigured, setBrokerConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    api.getBrokerStatus().then((res) => {
      if (!res.error) {
        setBrokerConfigured(res.data.configured);
      }
    });
  }, []);

  const handleToggle = async () => {
    if (status?.tradingEnabled) {
      setShowStopDialog(true);
    } else {
      await startTrading();
    }
  };

  const handleStopConfirm = async (mode: "hard" | "soft") => {
    await stopTrading(mode);
    setShowStopDialog(false);
  };

  const isActive = status?.tradingEnabled && status.status === "active";
  const isDisabled = isLoading || brokerConfigured === false;

  return (
    <div className="bg-bg-elevated p-6 rounded-lg border border-border-custom">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">AI Auto Trading</h3>
          <p className="text-sm text-text-muted mt-1">
            AI analyzes market and executes trades automatically
          </p>
        </div>

        <button
          onClick={handleToggle}
          disabled={isDisabled}
          className={`px-8 py-3 rounded-full font-bold text-lg transition-colors disabled:opacity-50 ${
            isActive
              ? "bg-theme-success text-white hover:opacity-90"
              : "bg-bg-surface text-text-secondary border border-border-custom hover:bg-bg-nav-hover"
          }`}
        >
          {isLoading ? "..." : isActive ? "ON" : "OFF"}
        </button>
      </div>

      <div className="flex items-center gap-2">
        <div
          className={`w-3 h-3 rounded-full ${
            isActive ? "bg-green-500 animate-pulse" : "bg-red-500"
          }`}
        />
        <span className="text-sm text-text-secondary">
          System is currently {isActive ? "ACTIVE" : "INACTIVE"}
        </span>
      </div>

      {brokerConfigured === false && (
        <p className="mt-3 text-sm text-yellow-400">
          Configure Alpaca API keys in{" "}
          <a href="/dashboard/settings" className="underline hover:text-yellow-300">
            Settings
          </a>{" "}
          to enable trading.
        </p>
      )}

      {error && (
        <p className="mt-2 text-xs text-red-400">{error}</p>
      )}

      {/* Stop Mode Dialog */}
      {showStopDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-bg-elevated p-6 rounded-lg border border-border-custom max-w-md">
            <h3 className="text-lg font-semibold text-text-primary mb-4">
              Stop AI Trading
            </h3>
            <p className="text-sm text-text-muted mb-6">
              Choose how to stop trading:
            </p>

            <div className="space-y-3">
              <button
                onClick={() => handleStopConfirm("soft")}
                className="w-full p-4 bg-bg-surface rounded border border-theme-primary text-left hover:bg-bg-nav-active"
              >
                <div className="font-semibold text-text-primary">🛡️ Soft Stop</div>
                <div className="text-sm text-text-muted mt-1">
                  Protect open positions with stop-loss/take-profit before stopping
                </div>
              </button>

              <button
                onClick={() => handleStopConfirm("hard")}
                className="w-full p-4 bg-bg-surface rounded border border-theme-danger text-left hover:bg-bg-nav-hover"
              >
                <div className="font-semibold text-text-primary">⛔ Hard Stop</div>
                <div className="text-sm text-text-muted mt-1">
                  Cancel all pending orders immediately (emergency stop)
                </div>
              </button>

              <button
                onClick={() => setShowStopDialog(false)}
                className="w-full p-2 text-sm text-text-muted hover:text-text-primary"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
