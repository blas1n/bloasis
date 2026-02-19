"use client";

import { useState } from "react";
import { useTradingControl } from "@/hooks/useTradingControl";

export function AITradingControl({ userId }: { userId: string }) {
  const { status, isLoading, startTrading, stopTrading } =
    useTradingControl(userId);
  const [showStopDialog, setShowStopDialog] = useState(false);

  const handleToggle = async () => {
    if (status?.tradingEnabled) {
      // OFF로 전환: Stop 모드 선택 다이얼로그 표시
      setShowStopDialog(true);
    } else {
      // ON으로 전환
      await startTrading();
    }
  };

  const handleStopConfirm = async (mode: "hard" | "soft") => {
    await stopTrading(mode);
    setShowStopDialog(false);
  };

  const isActive = status?.tradingEnabled && status.status === "active";

  return (
    <div className="bg-bg-elevated p-6 rounded-lg border border-border-custom">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">🤖 AI Auto Trading</h3>
          <p className="text-sm text-text-muted mt-1">
            AI analyzes market and executes trades automatically
          </p>
        </div>

        <button
          onClick={handleToggle}
          disabled={isLoading}
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
