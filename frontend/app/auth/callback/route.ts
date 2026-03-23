import { NextRequest, NextResponse } from "next/server";

/**
 * Auth callback handler.
 *
 * BSVibe Auth redirects here after login:
 *   /auth/callback?access_token=...&refresh_token=...&state=<original_path>
 *
 * Sets httpOnly cookies and redirects to the original page (from state param).
 */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const accessToken = searchParams.get("access_token");
  const refreshToken = searchParams.get("refresh_token");
  const state = searchParams.get("state") || "/dashboard";

  if (!accessToken || !refreshToken) {
    // Missing tokens — redirect to external login again
    const authUrl = process.env.BSVIBE_AUTH_URL || "https://auth.bsvibe.dev";
    const callbackUrl = `${request.nextUrl.origin}/auth/callback`;
    return NextResponse.redirect(
      `${authUrl}/login?redirect_uri=${encodeURIComponent(callbackUrl)}&state=${encodeURIComponent(state)}`
    );
  }

  const redirectUrl = new URL(state, request.nextUrl.origin);
  const response = NextResponse.redirect(redirectUrl);
  const secure = process.env.COOKIE_SECURE !== "false";

  response.cookies.set("access_token", accessToken, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: 3600,
  });

  response.cookies.set("refresh_token", refreshToken, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: 7 * 24 * 60 * 60,
  });

  return response;
}
