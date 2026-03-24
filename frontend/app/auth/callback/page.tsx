"use client";

import { useEffect } from "react";

/**
 * Auth callback page.
 *
 * BSVibe Auth redirects here with tokens in the hash fragment:
 *   /auth/callback#access_token=...&refresh_token=...&expires_in=3600&state=/dashboard
 *
 * Hash fragments are client-side only (never sent to server),
 * so we read them here and POST to an API route to set httpOnly cookies.
 */
export default function AuthCallbackPage() {
  useEffect(() => {
    handleCallback();
  }, []);

  async function handleCallback() {
    const hash = window.location.hash.substring(1); // remove leading #
    const params = new URLSearchParams(hash);

    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");
    const state = params.get("state") || "/dashboard";

    if (!accessToken || !refreshToken) {
      // No tokens — redirect to landing
      window.location.href = "/";
      return;
    }

    try {
      const res = await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accessToken, refreshToken }),
      });

      if (res.ok) {
        window.location.href = state;
      } else {
        window.location.href = "/";
      }
    } catch {
      window.location.href = "/";
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-base">
      <div className="text-center">
        <div className="animate-spin h-8 w-8 border-4 border-theme-primary border-t-transparent rounded-full mx-auto" />
        <p className="mt-4 text-text-secondary text-sm">Signing in...</p>
      </div>
    </div>
  );
}
