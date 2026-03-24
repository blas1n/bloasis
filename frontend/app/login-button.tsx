"use client";

const AUTH_URL = process.env.NEXT_PUBLIC_BSVIBE_AUTH_URL || "https://auth.bsvibe.dev";

export function LoginButton() {
  function handleClick() {
    const callbackUrl = `${window.location.origin}/auth/callback`;
    const loginUrl = `${AUTH_URL}/login?redirect_uri=${encodeURIComponent(callbackUrl)}&state=${encodeURIComponent("/dashboard")}`;
    window.location.href = loginUrl;
  }

  return (
    <button
      onClick={handleClick}
      className="inline-flex items-center px-8 py-3 text-base font-semibold rounded-lg text-white bg-theme-primary hover:opacity-90 transition-opacity"
    >
      Get Started
      <svg
        className="ml-2 h-5 w-5"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 7l5 5m0 0l-5 5m5-5H6"
        />
      </svg>
    </button>
  );
}
