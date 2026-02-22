"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { BrokerStatus } from "@/lib/types";

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [paper, setPaper] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [message, setMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const checkStatus = useCallback(async () => {
    const res = await api.getBrokerStatus();
    if (!res.error) {
      setStatus(res.data);
    }
  }, []);

  useEffect(() => {
    checkStatus();
  }, [checkStatus]);

  const handleSaveAndTest = async () => {
    if (!apiKey || !secretKey) {
      setMessage({ type: "error", text: "Both API Key and Secret Key are required." });
      return;
    }

    setSaving(true);
    setMessage(null);

    // 1. Save credentials
    const saveRes = await api.updateBrokerConfig({ apiKey, secretKey, paper });
    if (saveRes.error) {
      setMessage({ type: "error", text: saveRes.error });
      setSaving(false);
      return;
    }

    // 2. Test connection with saved credentials
    const testRes = await api.getBrokerStatus();
    if (testRes.error) {
      setMessage({ type: "error", text: testRes.error });
    } else if (!testRes.data.connected) {
      setMessage({
        type: "error",
        text: testRes.data.errorMessage || "Connection failed. Check your credentials.",
      });
      setStatus(testRes.data);
    } else {
      setMessage({
        type: "success",
        text: `Connected! Equity: $${testRes.data.equity.toLocaleString()} | Cash: $${testRes.data.cash.toLocaleString()}`,
      });
      setStatus(testRes.data);
      setApiKey("");
      setSecretKey("");
    }

    setSaving(false);
  };

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-bold text-text-primary mb-2">Settings</h1>
      <p className="text-text-secondary mb-8">
        Configure your broker connection for portfolio sync and trading.
      </p>

      {/* Connection Status */}
      <div className="bg-bg-elevated rounded-xl border border-border-custom p-6 mb-6">
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          Connection Status
        </h2>
        <div className="flex items-center gap-3">
          <div
            className={`h-3 w-3 rounded-full ${
              status?.connected
                ? "bg-green-500"
                : status?.configured
                ? "bg-yellow-500"
                : "bg-gray-500"
            }`}
          />
          <span className="text-text-primary">
            {status?.connected
              ? "Connected"
              : status?.configured
              ? "Configured (not verified)"
              : "Not configured"}
          </span>
        </div>
        {status?.connected && (
          <div className="mt-3 grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-text-secondary">Equity</span>
              <p className="text-text-primary font-medium">
                ${status.equity.toLocaleString()}
              </p>
            </div>
            <div>
              <span className="text-text-secondary">Cash</span>
              <p className="text-text-primary font-medium">
                ${status.cash.toLocaleString()}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Alpaca Credentials Form */}
      <div className="bg-bg-elevated rounded-xl border border-border-custom p-6 mb-6">
        <h2 className="text-lg font-semibold text-text-primary mb-4">
          Alpaca Credentials
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={status?.configured ? "********" : "Enter API Key"}
              className="w-full px-3 py-2 bg-bg-base border border-border-custom rounded-lg text-text-primary placeholder-text-secondary focus:outline-none focus:ring-2 focus:ring-theme-primary"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Secret Key
            </label>
            <input
              type="password"
              value={secretKey}
              onChange={(e) => setSecretKey(e.target.value)}
              placeholder={status?.configured ? "********" : "Enter Secret Key"}
              className="w-full px-3 py-2 bg-bg-base border border-border-custom rounded-lg text-text-primary placeholder-text-secondary focus:outline-none focus:ring-2 focus:ring-theme-primary"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="paper"
              checked={paper}
              onChange={(e) => setPaper(e.target.checked)}
              className="h-4 w-4 rounded border-border-custom"
            />
            <label htmlFor="paper" className="text-sm text-text-secondary">
              Paper Trading (recommended)
            </label>
          </div>
        </div>

        {/* Message */}
        {message && (
          <div
            className={`mt-4 p-3 rounded-lg text-sm ${
              message.type === "success"
                ? "bg-green-500/10 text-green-400 border border-green-500/20"
                : "bg-red-500/10 text-red-400 border border-red-500/20"
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Actions */}
        <div className="mt-6">
          <button
            onClick={handleSaveAndTest}
            disabled={saving}
            className="px-4 py-2 bg-theme-primary text-white rounded-lg font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {saving ? "Testing..." : "Save & Test Connection"}
          </button>
        </div>
      </div>

      <p className="text-xs text-text-secondary">
        Credentials are encrypted at rest and never logged.
        Get your API keys from{" "}
        <a
          href="https://app.alpaca.markets/paper/dashboard/overview"
          target="_blank"
          rel="noopener noreferrer"
          className="text-theme-primary hover:underline"
        >
          Alpaca Dashboard
        </a>
        .
      </p>
    </div>
  );
}
