import { NextRequest, NextResponse } from "next/server";

const BSVIBE_AUTH_URL = process.env.BSVIBE_AUTH_URL || "https://auth.bsvibe.dev";

/**
 * Get the external origin from the request headers.
 * Uses X-Forwarded-Host/Proto if behind a reverse proxy, otherwise falls back to Host header.
 */
function getExternalOrigin(request: NextRequest): string {
  const proto = request.headers.get("x-forwarded-proto") || "http";
  const host =
    request.headers.get("x-forwarded-host") || request.headers.get("host");
  if (host) {
    return `${proto}://${host}`;
  }
  return request.nextUrl.origin;
}

export function middleware(request: NextRequest) {
  const accessToken = request.cookies.get("access_token")?.value;
  const { pathname } = request.nextUrl;

  const isPublic =
    pathname === "/" || // landing page
    pathname.startsWith("/auth/") || // callback handler
    pathname === "/health" ||
    pathname.startsWith("/api/"); // API proxy handles its own auth

  // Redirect authenticated users from landing to dashboard
  if (pathname === "/" && accessToken) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  // Protect all non-public routes — redirect to BSVibe Auth
  if (!isPublic && !accessToken) {
    const origin = getExternalOrigin(request);
    const callbackUrl = `${origin}/auth/callback`;
    const state = pathname === "/" ? "/dashboard" : pathname;
    const loginUrl = `${BSVIBE_AUTH_URL}/login?redirect_uri=${encodeURIComponent(callbackUrl)}&state=${encodeURIComponent(state)}`;
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
