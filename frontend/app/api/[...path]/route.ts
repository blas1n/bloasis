import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_URL || "http://localhost:8000";

/**
 * API proxy route to forward requests to FastAPI backend.
 * Supports GET, POST, PUT, PATCH, DELETE methods.
 */

async function proxyRequest(
  request: NextRequest,
  params: { path: string[] },
  method: string
) {
  const path = params.path.join("/");
  const url = `${API_BASE_URL}/${path}${request.nextUrl.search}`;

  // Forward JWT token from httpOnly cookie
  const headers: Record<string, string> = {};
  const accessToken = request.cookies.get("access_token")?.value;
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }

  const fetchOptions: RequestInit = {
    method,
    headers,
    signal: AbortSignal.timeout(30000),
  };

  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    try {
      const text = await request.text();
      if (text.trim()) fetchOptions.body = text;
    } catch {
      // no body — proceed without
    }
  }

  try {
    let response = await fetch(url, fetchOptions);

    // If 401, try refreshing the token and retry once
    if (response.status === 401 && accessToken) {
      const refreshToken = request.cookies.get("refresh_token")?.value;
      if (refreshToken) {
        const refreshRes = await fetch(
          `${API_BASE_URL}/v1/auth/tokens/refresh`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refreshToken }),
          }
        );
        if (refreshRes.ok) {
          const refreshData = await refreshRes.json();
          headers["Authorization"] = `Bearer ${refreshData.accessToken}`;
          fetchOptions.headers = headers;
          response = await fetch(url, fetchOptions);

          // Always persist new token after successful refresh
          const data = response.ok ? await response.json() : { error: "Request failed" };
          const nextRes = NextResponse.json(data, {
            status: response.status,
          });
          nextRes.cookies.set("access_token", refreshData.accessToken, {
            httpOnly: true,
            secure: process.env.NODE_ENV === "production",
            sameSite: "lax",
            path: "/",
            maxAge: 30 * 60,
          });
          return nextRes;
        }
      }
    }

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Backend ${method} error (${response.status}):`, errorText);
      return NextResponse.json(
        { error: "Request failed" },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`Backend ${method} failed for ${path}:`, error);
    return NextResponse.json(
      {
        error: "Service unavailable",
        message: "Backend service is currently unavailable. Please try again later.",
      },
      { status: 503 }
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, "GET");
}

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, "POST");
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, "PUT");
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, "PATCH");
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  return proxyRequest(request, params, "DELETE");
}
