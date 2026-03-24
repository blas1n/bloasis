import { NextRequest, NextResponse } from "next/server";

/**
 * Get current user info by decoding the JWT access token.
 * No backend call needed — all info is in the token claims.
 */
export async function GET(request: NextRequest) {
  const accessToken = request.cookies.get("access_token")?.value;

  if (!accessToken) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  try {
    // Decode JWT payload without verification (already verified by backend on API calls)
    const parts = accessToken.split(".");
    if (parts.length !== 3) {
      return NextResponse.json({ error: "Invalid token" }, { status: 401 });
    }

    const payload = JSON.parse(
      Buffer.from(parts[1], "base64url").toString("utf-8")
    );

    const userId = payload.sub || "";
    const email = payload.email || "";
    const userMetadata = payload.user_metadata || {};
    const name = userMetadata.name || email.split("@")[0] || "";

    if (!userId) {
      return NextResponse.json({ error: "Invalid token" }, { status: 401 });
    }

    // Check expiration
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      return NextResponse.json({ error: "Token expired" }, { status: 401 });
    }

    return NextResponse.json({ userId, name, email });
  } catch {
    return NextResponse.json({ error: "Invalid session" }, { status: 401 });
  }
}
