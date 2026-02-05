/**
 * API client for BLOASIS backend services via Kong Gateway.
 */

import type {
  ApiResponse,
  CandidateSymbolsResponse,
  MarketRegimeResponse,
  PersonalizedStrategyResponse,
  PortfolioSummary,
  PositionsResponse,
  SectorAnalysisResponse,
  StockPicksResponse,
  TradeHistoryResponse,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  async getMarketRegime(): Promise<ApiResponse<MarketRegimeResponse>> {
    return this.request<MarketRegimeResponse>("/v1/market-regime/current");
  }

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
}

export const api = new ApiClient();
