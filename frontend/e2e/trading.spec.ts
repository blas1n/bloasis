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

const FRONTEND_URL = 'http://localhost:3000';
const API_URL = 'http://localhost:8000';
const DEMO_EMAIL = 'demo@bloasis.ai';
const DEMO_PASSWORD = 'demo1234';
const USER_ID = '00000000-0000-0000-0000-000000000001';

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

    // Step 3: Verify the filled XOM trade is present
    expect(tradesData.trades).toBeDefined();
    expect(tradesData.trades.length).toBeGreaterThan(0);

    const xomTrade = tradesData.trades.find(
      (t: { symbol: string }) => t.symbol === 'XOM'
    );
    expect(xomTrade).toBeDefined();
    console.log(`✅ Found XOM trade: ${xomTrade.side.toUpperCase()} × ${xomTrade.qty} @ $${xomTrade.price}`);

    // Step 4: Verify trade details match what the user sees on screen
    // TradingLog shows: "BUY XOM × {qty}" + "${price}" + "EXECUTED" badge
    expect(xomTrade.side).toBe('buy');
    expect(Number(xomTrade.qty)).toBeGreaterThan(0);
    expect(Number(xomTrade.price)).toBeGreaterThan(0);
    expect(xomTrade.executedAt).toBeTruthy();

    // Step 5: Verify AI reasoning is displayed
    expect(xomTrade.aiReason).toBeTruthy();

    console.log('\n✅ VERIFIED: User can see the Alpaca-filled XOM trade on the Trading page');
    console.log(`   BUY XOM × ${xomTrade.qty} @ $${xomTrade.price}`);
    console.log(`   Executed: ${xomTrade.executedAt}`);
    console.log(`   AI Reason: ${xomTrade.aiReason}`);
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

    // Verify trade exists and is filled
    expect(data.trades.length).toBeGreaterThan(0);

    const xom = data.trades.find((t: { symbol: string }) => t.symbol === 'XOM');
    expect(xom).toBeDefined();
    expect(xom.side).toBe('buy');
    expect(Number(xom.price)).toBeCloseTo(159.29, 0);

    // Verify AI reasoning is present (not empty)
    expect(xom.aiReason).toBeTruthy();
    console.log(`✅ Backend confirms: XOM BUY filled @ $${xom.price}`);
    console.log(`   AI Reason: ${xom.aiReason}`);
  });
});
