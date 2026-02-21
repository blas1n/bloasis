import { NextRequest, NextResponse } from "next/server";

const API_BASE_URL = process.env.API_URL || "http://localhost:8000";

/**
 * API proxy route to forward requests to Envoy Gateway.
 * This allows the frontend to call APIs without CORS issues in development.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const path = params.path.join("/");
  const url = `${API_BASE_URL}/${path}${request.nextUrl.search}`;

  try {
    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
      },
      signal: AbortSignal.timeout(30000), // 3s timeout
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Envoy Gateway error (${response.status}):`, errorText);
      return NextResponse.json(
        {
          error: "Backend service error",
          details: errorText,
          status: response.status,
        },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`Envoy Gateway connection failed for ${path}:`, error);

    // Return clear error message
    return NextResponse.json(
      {
        error: "Envoy Gateway unavailable",
        message:
          "Cannot connect to Envoy Gateway at " + API_BASE_URL + ". Please ensure Envoy Gateway is running.",
        troubleshooting: {
          checkServices: "Make sure backend services are running",
          kongStatus: "Verify Envoy Gateway is accessible at " + API_BASE_URL,
          docs: "See BLOASIS architecture documentation for setup",
        },
      },
      { status: 503 } // Service Unavailable
    );
  }
}


export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const path = params.path.join("/");
  const url = `${API_BASE_URL}/${path}`;

  let body: unknown = {};
  try {
    const text = await request.text();
    if (text.trim()) body = JSON.parse(text);
  } catch {
    // no body or invalid JSON — proceed with empty object
  }

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30000),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: "Backend service error", details: errorText },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`Envoy Gateway POST failed for ${path}:`, error);
    return NextResponse.json(
      {
        error: "Envoy Gateway unavailable",
        message: "Cannot connect to backend services. Please ensure Envoy Gateway is running.",
      },
      { status: 503 }
    );
  }
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const path = params.path.join("/");
  const url = `${API_BASE_URL}/${path}`;

  let body: unknown = {};
  try {
    const text = await request.text();
    if (text.trim()) body = JSON.parse(text);
  } catch {
    // no body or invalid JSON — proceed with empty object
  }

  try {
    const response = await fetch(url, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30000),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: "Backend service error", details: errorText },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error(`Envoy Gateway PATCH failed for ${path}:`, error);
    return NextResponse.json(
      {
        error: "Envoy Gateway unavailable",
        message: "Cannot connect to backend services. Please ensure Envoy Gateway is running.",
      },
      { status: 503 }
    );
  }
}
