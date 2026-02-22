/**
 * API client for BLOASIS backend services via Kong Gateway.
 */

import type {
  ApiResponse,
  BrokerConfig,
  BrokerStatus,
  CandidateSymbolsResponse,
  MarketRegimeResponse,
  PersonalizedStrategyResponse,
  PortfolioSummary,
  PositionsResponse,
  SectorAnalysisResponse,
  StockPicksResponse,
  SyncResponse,
  TradeHistoryResponse,
  TradingStatus,
  TradingControlResponse,
  UserPreferences,
  RiskProfile,
} from "./types";

// In browser: go through Next.js API proxy (/api/[...path] → Envoy Gateway)
// NEXT_PUBLIC_API_URL can override (e.g. for production direct access)
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "/api";

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
        },
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      return { data };
    } catch (error) {
      return { data: null as T, error: String(error) };
    }
  }

  // Portfolio endpoints
  async getPortfolioSummary(userId: string): Promise<ApiResponse<PortfolioSummary>> {
    return this.request<PortfolioSummary>(`/v1/portfolio/${userId}/summary`);
  }

  async getPositions(userId: string): Promise<ApiResponse<PositionsResponse>> {
    return this.request<PositionsResponse>(`/v1/portfolio/${userId}/positions`);
  }

  async getTradeHistory(
    userId: string,
    options?: { symbol?: string; limit?: number }
  ): Promise<ApiResponse<TradeHistoryResponse>> {
    const params = new URLSearchParams();
    if (options?.symbol) params.set("symbol", options.symbol);
    if (options?.limit) params.set("limit", options.limit.toString());
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<TradeHistoryResponse>(
      `/v1/portfolio/${userId}/trades${query}`
    );
  }

  // Market Regime endpoints
  async getCurrentRegime(): Promise<ApiResponse<MarketRegimeResponse>> {
    return this.request<MarketRegimeResponse>("/v1/market-regime/current");
  }

  // Classification endpoints (Stage 1-2)
  async getSectorAnalysis(regime: string): Promise<ApiResponse<SectorAnalysisResponse>> {
    return this.request<SectorAnalysisResponse>(
      `/v1/classification/sectors?regime=${regime}`
    );
  }

  async getCandidateSymbols(): Promise<ApiResponse<CandidateSymbolsResponse>> {
    return this.request<CandidateSymbolsResponse>("/v1/classification/candidates");
  }

  // Strategy endpoint (Stage 3 + AI Flow)
  async getPersonalizedStrategy(userId: string): Promise<ApiResponse<PersonalizedStrategyResponse>> {
    return this.request<PersonalizedStrategyResponse>("/v1/strategy/personalized", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  }

  async getStockPicks(
    userId: string,
    maxPicks: number = 15
  ): Promise<ApiResponse<StockPicksResponse>> {
    return this.request<StockPicksResponse>("/v1/strategy/picks", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, max_picks: maxPicks }),
    });
  }

  // ========================================================================
  // Trading Control APIs
  // ========================================================================

  async startTrading(userId: string): Promise<ApiResponse<TradingControlResponse>> {
    return this.request<TradingControlResponse>(
      `/v1/users/${userId}/trading/start`,
      { method: "POST" }
    );
  }

  async stopTrading(
    userId: string,
    stopMode: "hard" | "soft" = "soft"
  ): Promise<ApiResponse<TradingControlResponse>> {
    return this.request<TradingControlResponse>(
      `/v1/users/${userId}/trading/stop`,
      {
        method: "POST",
        body: JSON.stringify({ stop_mode: stopMode }),
      }
    );
  }

  async getTradingStatus(userId: string): Promise<ApiResponse<TradingStatus>> {
    return this.request<TradingStatus>(`/v1/users/${userId}/trading/status`);
  }

  // ========================================================================
  // User Preferences APIs
  // ========================================================================

  async getUserPreferences(userId: string): Promise<ApiResponse<UserPreferences>> {
    const result = await this.request<{ preferences: UserPreferences }>(
      `/v1/users/${userId}/preferences`
    );
    if (result.data?.preferences) {
      return { data: result.data.preferences };
    }
    return { data: null as unknown as UserPreferences, error: result.error };
  }

  async updateRiskProfile(
    userId: string,
    riskProfile: RiskProfile
  ): Promise<ApiResponse<UserPreferences>> {
    const result = await this.request<{ preferences: UserPreferences }>(
      `/v1/users/${userId}/preferences`,
      {
        method: "PATCH",
        body: JSON.stringify({
          preferences: { risk_profile: riskProfile },
        }),
      }
    );
    if (result.data?.preferences) {
      return { data: result.data.preferences };
    }
    return { data: null as unknown as UserPreferences, error: result.error };
  }
  // ========================================================================
  // Broker Config APIs
  // ========================================================================

  async updateBrokerConfig(
    config: BrokerConfig
  ): Promise<ApiResponse<{ success: boolean }>> {
    return this.request<{ success: boolean }>("/v1/settings/broker", {
      method: "PATCH",
      body: JSON.stringify({
        alpaca_api_key: config.apiKey,
        alpaca_secret_key: config.secretKey,
        paper: config.paper,
      }),
    });
  }

  async getBrokerStatus(): Promise<ApiResponse<BrokerStatus>> {
    return this.request<BrokerStatus>("/v1/settings/broker/status");
  }

  // ========================================================================
  // Portfolio Sync APIs
  // ========================================================================

  async syncWithAlpaca(userId: string): Promise<ApiResponse<SyncResponse>> {
    return this.request<SyncResponse>(`/v1/portfolio/${userId}/sync`, {
      method: "POST",
    });
  }
}

export const api = new ApiClient();
