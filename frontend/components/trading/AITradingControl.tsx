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
    <div className="bg-slate-800 p-6 rounded-lg border border-slate-700">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white">🤖 AI Auto Trading</h3>
          <p className="text-sm text-slate-400 mt-1">
            AI analyzes market and executes trades automatically
          </p>
        </div>

        <button
          onClick={handleToggle}
          disabled={isLoading}
          className={`px-8 py-3 rounded-full font-bold text-lg transition-colors disabled:opacity-50 ${
            isActive
              ? "hover:opacity-90"
              : "bg-slate-600 text-slate-200 hover:bg-slate-500"
          }`}
          style={isActive ? { backgroundColor: "#00E676", color: "#ffffff" } : undefined}
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
        <span className="text-sm text-slate-300">
          System is currently {isActive ? "ACTIVE" : "INACTIVE"}
        </span>
      </div>

      {/* Stop Mode Dialog */}
      {showStopDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-slate-800 p-6 rounded-lg border border-slate-700 max-w-md">
            <h3 className="text-lg font-semibold text-white mb-4">
              Stop AI Trading
            </h3>
            <p className="text-sm text-slate-400 mb-6">
              Choose how to stop trading:
            </p>

            <div className="space-y-3">
              <button
                onClick={() => handleStopConfirm("soft")}
                className="w-full p-4 bg-slate-700 rounded border border-blue-500 text-left hover:bg-slate-600"
              >
                <div className="font-semibold text-white">🛡️ Soft Stop</div>
                <div className="text-sm text-slate-400 mt-1">
                  Protect open positions with stop-loss/take-profit before stopping
                </div>
              </button>

              <button
                onClick={() => handleStopConfirm("hard")}
                className="w-full p-4 bg-slate-700 rounded border border-red-500 text-left hover:bg-slate-600"
              >
                <div className="font-semibold text-white">⛔ Hard Stop</div>
                <div className="text-sm text-slate-400 mt-1">
                  Cancel all pending orders immediately (emergency stop)
                </div>
              </button>

              <button
                onClick={() => setShowStopDialog(false)}
                className="w-full p-2 text-sm text-slate-400 hover:text-white"
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
