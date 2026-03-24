import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  const refreshToken = request.cookies.get("refresh_token")?.value;
  if (!refreshToken) {
    return NextResponse.json({ error: "No refresh token" }, { status: 401 });
  }

  try {
    const res = await fetch(`${API_BASE_URL}/v1/auth/tokens/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refreshToken }),
    });

    if (!res.ok) {
      const response = NextResponse.json(
        { error: "Refresh failed" },
        { status: 401 }
      );
      response.cookies.set("access_token", "", { maxAge: 0, path: "/" });
      response.cookies.set("refresh_token", "", { maxAge: 0, path: "/" });
      response.cookies.set("user_info", "", { maxAge: 0, path: "/" });
      return response;
    }

    const data = await res.json();
    const response = NextResponse.json({ success: true });

    const secure = process.env.COOKIE_SECURE !== "false";

    response.cookies.set("access_token", data.accessToken, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      maxAge: 3600,
    });

    // Supabase rotates refresh tokens — update cookie
    if (data.refreshToken) {
      response.cookies.set("refresh_token", data.refreshToken, {
        httpOnly: true,
        secure,
        sameSite: "lax",
        path: "/",
        maxAge: 7 * 24 * 60 * 60,
      });
    }

    return response;
  } catch {
    return NextResponse.json(
      { error: "Service unavailable" },
      { status: 503 }
    );
  }
}
