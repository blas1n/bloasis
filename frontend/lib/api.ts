/**
 * API client for BLOASIS backend (FastAPI monolith).
 */

import type {
  ApiResponse,
  BrokerConfig,
  BrokerStatus,
  MarketRegimeResponse,
  PersonalizedStrategyResponse,
  PortfolioSummary,
  PositionsResponse,
  SyncResponse,
  TradeHistoryResponse,
  TradingStatus,
  TradingControlResponse,
  UserPreferences,
  RiskProfile,
} from "./types";

// In browser: go through Next.js API proxy (/api/[...path] → FastAPI)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "/api";

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

  // ========================================================================
  // Portfolio — /v1/portfolios/{userId}/*
  // ========================================================================

  async getPortfolioSummary(
    userId: string
  ): Promise<ApiResponse<PortfolioSummary>> {
    return this.request<PortfolioSummary>(`/v1/portfolios/${userId}`);
  }

  async getPositions(userId: string): Promise<ApiResponse<PositionsResponse>> {
    return this.request<PositionsResponse>(
      `/v1/portfolios/${userId}/positions`
    );
  }

  async getTradeHistory(
    userId: string,
    options?: { limit?: number }
  ): Promise<ApiResponse<TradeHistoryResponse>> {
    const params = new URLSearchParams();
    if (options?.limit) params.set("limit", options.limit.toString());
    const query = params.toString() ? `?${params.toString()}` : "";
    return this.request<TradeHistoryResponse>(
      `/v1/portfolios/${userId}/trades${query}`
    );
  }

  async syncWithAlpaca(userId: string): Promise<ApiResponse<SyncResponse>> {
    return this.request<SyncResponse>(`/v1/portfolios/${userId}/sync`, {
      method: "POST",
    });
  }

  // ========================================================================
  // Market — /v1/market/*
  // ========================================================================

  async getCurrentRegime(): Promise<ApiResponse<MarketRegimeResponse>> {
    return this.request<MarketRegimeResponse>("/v1/market/regimes/current");
  }

  // ========================================================================
  // Signals — /v1/users/{userId}/signals
  // ========================================================================

  async getSignals(
    userId: string
  ): Promise<ApiResponse<PersonalizedStrategyResponse>> {
    return this.request<PersonalizedStrategyResponse>(
      `/v1/users/${userId}/signals`
    );
  }

  async triggerAnalysis(
    userId: string
  ): Promise<ApiResponse<PersonalizedStrategyResponse>> {
    return this.request<PersonalizedStrategyResponse>(
      `/v1/users/${userId}/signals`,
      { method: "POST" }
    );
  }

  // ========================================================================
  // Trading Control — /v1/users/{userId}/trading
  // ========================================================================

  async getTradingStatus(userId: string): Promise<ApiResponse<TradingStatus>> {
    return this.request<TradingStatus>(`/v1/users/${userId}/trading`);
  }

  async startTrading(
    userId: string
  ): Promise<ApiResponse<TradingControlResponse>> {
    return this.request<TradingControlResponse>(
      `/v1/users/${userId}/trading`,
      { method: "POST" }
    );
  }

  async stopTrading(
    userId: string,
    stopMode: "hard" | "soft" = "soft"
  ): Promise<ApiResponse<TradingControlResponse>> {
    return this.request<TradingControlResponse>(
      `/v1/users/${userId}/trading`,
      {
        method: "DELETE",
        body: JSON.stringify({ mode: stopMode }),
      }
    );
  }

  // ========================================================================
  // User Preferences — /v1/users/{userId}/preferences
  // ========================================================================

  async getUserPreferences(
    userId: string
  ): Promise<ApiResponse<UserPreferences>> {
    return this.request<UserPreferences>(`/v1/users/${userId}/preferences`);
  }

  async updatePreferences(
    userId: string,
    prefs: UserPreferences
  ): Promise<ApiResponse<UserPreferences>> {
    return this.request<UserPreferences>(`/v1/users/${userId}/preferences`, {
      method: "PUT",
      body: JSON.stringify(prefs),
    });
  }

  // ========================================================================
  // Broker Config — /v1/users/{userId}/broker
  // ========================================================================

  async updateBrokerConfig(
    userId: string,
    config: BrokerConfig
  ): Promise<ApiResponse<BrokerStatus>> {
    return this.request<BrokerStatus>(`/v1/users/${userId}/broker`, {
      method: "PUT",
      body: JSON.stringify({
        apiKey: config.apiKey,
        secretKey: config.secretKey,
        paper: config.paper,
      }),
    });
  }

  async getBrokerStatus(userId: string): Promise<ApiResponse<BrokerStatus>> {
    return this.request<BrokerStatus>(`/v1/users/${userId}/broker`);
  }
}

export const api = new ApiClient();
