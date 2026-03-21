"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { login } = useAuth();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const err = await login(email, password);
    if (err) {
      setError(err);
      setLoading(false);
    } else {
      router.push("/dashboard");
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-base">
      <div className="w-full max-w-sm p-8 bg-bg-elevated rounded-xl border border-border-custom">
        <h1 className="text-2xl font-bold text-text-primary mb-2 text-center">
          BLOASIS
        </h1>
        <p className="text-text-secondary text-sm text-center mb-8">
          AI-powered trading platform
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2 bg-bg-base border border-border-custom rounded-lg text-text-primary placeholder-text-secondary focus:outline-none focus:ring-2 focus:ring-theme-primary"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-3 py-2 bg-bg-base border border-border-custom rounded-lg text-text-primary placeholder-text-secondary focus:outline-none focus:ring-2 focus:ring-theme-primary"
              placeholder="Enter password"
            />
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20 text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-theme-primary text-white rounded-lg font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
