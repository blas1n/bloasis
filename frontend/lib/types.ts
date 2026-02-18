/**
 * TypeScript types for BLOASIS frontend.
 */

// Portfolio Types
export interface PortfolioSummary {
  totalEquity: number;
  cash: number;
  buyingPower: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  realizedPnl: number;
  dailyPnl: number;
  dailyPnlPct: number;
  positionCount: number;
}

export interface Position {
  symbol: string;
  quantity: number;
  avgCost: number;
  currentPrice: number;
  currentValue: number;
  unrealizedPnl: number;
  unrealizedPnlPercent: number;
  currency: string;
}

export interface PositionsResponse {
  userId: string;
  positions: Position[];
}

// Market Regime Types
export type RegimeType = "risk_on" | "risk_off" | "crisis" | "recovery";
export type RiskLevel = "low" | "medium" | "high";

export interface MarketRegimeIndicators {
  vix: number;
  sp500Trend: string;
  yieldCurve: string;
  creditSpreads: string;
}

export interface MarketRegimeResponse {
  regime: RegimeType;
  confidence: number;
  timestamp: string;
  trigger: string; // What triggered this classification
  reasoning: string; // AI-generated explanation
  riskLevel: RiskLevel; // Note: API returns "risk_level" (snake_case), Envoy transcodes to camelCase
  indicators: MarketRegimeIndicators;
}

// Classification Types
export interface SectorAllocation {
  sector: string;
  weight: number;
  rationale: string;
}

export interface SectorAnalysisResponse {
  regime: string;
  sectors: SectorAllocation[];
  timestamp: string;
}

export interface CandidateSymbol {
  symbol: string;
  sector: string;
  score: number;
  factors: Record<string, number>;
}

export interface CandidateSymbolsResponse {
  candidates: CandidateSymbol[];
  timestamp: string;
}

// Strategy Types
export interface Signal {
  symbol: string;
  action: "buy" | "sell" | "hold";
  confidence: number;
  sizeRecommendation: number;
  stopLoss: number;
  takeProfit: number;
  rationale: string;
}

export interface PersonalizedStrategyResponse {
  userId: string;
  signals: Signal[];
  riskBudget: number;
  timestamp: string;
}

export interface StockPick {
  symbol: string;
  sector: string;
  score: number;
  action: "buy" | "hold";
  targetAllocation: number;
  rationale: string;
}

export interface StockPicksResponse {
  userId: string;
  picks: StockPick[];
  timestamp: string;
}

// Trade Types
export interface Trade {
  orderId: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  commission: number;
  executedAt: string;
  realizedPnl: number;
  aiReason?: string;  // AI-generated reasoning for this trade
}

export interface TradeHistoryResponse {
  trades: Trade[];
  totalRealizedPnl: number;
  nextPollMs?: number;
}

// API Response wrapper
export interface ApiResponse<T> {
  data: T;
  error?: string;
}

// ============================================================================
// AI Trading Control Types
// ============================================================================

export interface TradingStatus {
  tradingEnabled: boolean;
  status: "active" | "soft_stopped" | "hard_stopped" | "inactive";
  lastChanged: string;
  nextPollMs?: number;
}

export interface TradingControlResponse {
  success: boolean;
  message: string;
  ordersCancelled?: number;
  timestamp: string;
}

// ============================================================================
// User Preferences Extension
// ============================================================================

export type RiskProfile = "conservative" | "moderate" | "aggressive";

export interface UserPreferences {
  userId: string;
  riskProfile: RiskProfile;
  maxPortfolioRisk: string;
  maxPositionSize: string;
  preferredSectors: string[];
  enableNotifications: boolean;
  tradingEnabled: boolean;
}
