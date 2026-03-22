import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  const accessToken = request.cookies.get("access_token")?.value;

  // Best-effort backend logout via access token
  if (accessToken) {
    try {
      await fetch(`${API_BASE_URL}/v1/auth/tokens`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
    } catch {
      // ignore — cookies will be cleared regardless
    }
  }

  const response = NextResponse.json({ success: true });

  // Clear all auth cookies
  response.cookies.set("access_token", "", { maxAge: 0, path: "/" });
  response.cookies.set("refresh_token", "", { maxAge: 0, path: "/" });
  response.cookies.set("user_info", "", { maxAge: 0, path: "/" });

  return response;
}
