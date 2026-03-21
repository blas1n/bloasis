import { test, expect } from '@playwright/test';

/**
 * E2E test: Verify trades are visible from a real user's perspective.
 *
 * Since this devcontainer has no browser installed, we use Playwright's API
 * testing to exercise the exact same HTTP flow the user's browser performs:
 *   1. POST /api/auth/login → get session cookie
 *   2. GET /api/v1/portfolios/{userId}/trades → verify trade data
 *
 * This validates the FULL stack: Frontend proxy → FastAPI → DB → Response
 */

const FRONTEND_URL = process.env.E2E_FRONTEND_URL ?? 'http://localhost:3000';
const API_URL = process.env.E2E_API_URL ?? 'http://localhost:8000';

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing required env var: ${name}. See frontend/.env.example for E2E config.`,
    );
  }
  return value;
}

const DEMO_EMAIL = requireEnv('E2E_DEMO_EMAIL');
const DEMO_PASSWORD = requireEnv('E2E_DEMO_PASSWORD');
const USER_ID = requireEnv('E2E_USER_ID');

test.describe('Trading flow — user perspective (API)', () => {

  test('user can login and see filled trades via frontend proxy', async ({ request }) => {
    // Step 1: User opens login page and submits credentials
    // The frontend proxy at /api/auth/login forwards to FastAPI and sets cookies
    const loginResponse = await request.post(`${FRONTEND_URL}/api/auth/login`, {
      data: { email: DEMO_EMAIL, password: DEMO_PASSWORD },
    });

    expect(loginResponse.ok()).toBeTruthy();
    const loginData = await loginResponse.json();
    console.log(`✅ Login successful: ${loginData.name} (${loginData.userId})`);
    expect(loginData.userId).toBe(USER_ID);

    // Step 2: User navigates to Trading page — frontend calls trades API
    // The proxy at /api/v1/... forwards to FastAPI with the auth cookie
    const tradesResponse = await request.get(
      `${FRONTEND_URL}/api/v1/portfolios/${USER_ID}/trades`
    );

    expect(tradesResponse.ok()).toBeTruthy();
    const tradesData = await tradesResponse.json();
    console.log(`✅ Trades API response:`, JSON.stringify(tradesData, null, 2));

    // Step 3: Verify at least one trade is present
    expect(tradesData.trades).toBeDefined();
    expect(tradesData.trades.length).toBeGreaterThan(0);

    const firstTrade = tradesData.trades[0];

    // Step 4: Verify trade has the required fields for display
    expect(firstTrade.symbol).toBeTruthy();
    expect(['buy', 'sell']).toContain(firstTrade.side);
    expect(Number(firstTrade.qty)).toBeGreaterThan(0);
    expect(Number(firstTrade.price)).toBeGreaterThan(0);
    expect(firstTrade.executedAt).toBeTruthy();

    console.log(`✅ Found trade: ${firstTrade.side.toUpperCase()} ${firstTrade.symbol} × ${firstTrade.qty} @ $${firstTrade.price}`);
    console.log(`   Executed: ${firstTrade.executedAt}`);
    if (firstTrade.aiReason) {
      console.log(`   AI Reason: ${firstTrade.aiReason}`);
    }
  });

  test('backend API directly returns filled trade', async ({ request }) => {
    // Direct API test: authenticate and fetch trades from FastAPI
    const authResponse = await request.post(`${API_URL}/v1/auth/tokens`, {
      data: { email: DEMO_EMAIL, password: DEMO_PASSWORD },
    });

    expect(authResponse.ok()).toBeTruthy();
    const authData = await authResponse.json();
    const token = authData.accessToken;

    // Fetch trades
    const tradesResponse = await request.get(
      `${API_URL}/v1/portfolios/${USER_ID}/trades`,
      { headers: { Authorization: `Bearer ${token}` } }
    );

    expect(tradesResponse.ok()).toBeTruthy();
    const data = await tradesResponse.json();

    // Verify at least one trade exists with valid structure
    expect(data.trades.length).toBeGreaterThan(0);

    const trade = data.trades[0];
    expect(trade.symbol).toBeTruthy();
    expect(['buy', 'sell']).toContain(trade.side);
    expect(Number(trade.qty)).toBeGreaterThan(0);
    expect(Number(trade.price)).toBeGreaterThan(0);

    console.log(`✅ Backend confirms: ${trade.side.toUpperCase()} ${trade.symbol} @ $${trade.price}`);
    if (trade.aiReason) {
      console.log(`   AI Reason: ${trade.aiReason}`);
    }
  });
});
