import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_URL || "http://localhost:8000";

export async function GET(request: NextRequest) {
  const accessToken = request.cookies.get("access_token")?.value;

  if (!accessToken) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  try {
    const res = await fetch(`${API_BASE_URL}/v1/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    if (!res.ok) {
      return NextResponse.json({ error: "Invalid session" }, { status: 401 });
    }

    const userInfo = await res.json();
    return NextResponse.json(userInfo);
  } catch {
    return NextResponse.json({ error: "Service unavailable" }, { status: 503 });
  }
}
