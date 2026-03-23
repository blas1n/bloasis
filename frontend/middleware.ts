import { NextRequest, NextResponse } from "next/server";

const BSVIBE_AUTH_URL = process.env.BSVIBE_AUTH_URL || "https://auth.bsvibe.dev";

export function middleware(request: NextRequest) {
  const accessToken = request.cookies.get("access_token")?.value;
  const { pathname } = request.nextUrl;

  const isPublic =
    pathname.startsWith("/auth/") || // callback handler
    pathname === "/health" ||
    pathname.startsWith("/api/"); // API proxy handles its own auth

  // Protect all non-public routes — redirect to BSVibe Auth
  if (!isPublic && !accessToken) {
    const callbackUrl = `${request.nextUrl.origin}/auth/callback`;
    const state = pathname === "/" ? "/dashboard" : pathname;
    const loginUrl = `${BSVIBE_AUTH_URL}/login?redirect_uri=${encodeURIComponent(callbackUrl)}&state=${encodeURIComponent(state)}`;
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
