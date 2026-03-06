/**
 * TypeScript types for BLOASIS frontend.
 *
 * Backend returns camelCase JSON (via CamelJSONResponse).
 */

// ============================================================================
// Auth Types
// ============================================================================

export interface AuthUser {
  userId: string;
  name: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  userId: string;
  name: string;
}

// Portfolio Types
export interface PortfolioSummary {
  userId: string;
  totalValue: number;
  totalEquity: number;
  cashBalance: number;
  buyingPower: number;
  investedValue: number;
  marketValue: number;
  totalReturn: number;
  totalReturnAmount: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  realizedPnl: number;
  dailyPnl: number;
  dailyPnlPct: number;
  positionCount: number;
  currency: string;
}

export interface Position {
  symbol: string;
  quantity: number;
  avgCost: number;
  currentPrice: number;
  currentValue: number;
  unrealizedPnl: number;
  unrealizedPnlPercent: number;
  sector: string;
  currency: string;
}

export interface PositionsResponse {
  userId: string;
  positions: Position[];
}

// Market Regime Types
export type RegimeType = "bull" | "bear" | "sideways" | "crisis" | "recovery";
export type RiskLevel = "low" | "medium" | "high" | "extreme";

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
  trigger: string;
  reasoning: string;
  riskLevel: RiskLevel;
  indicators: MarketRegimeIndicators;
}

// Strategy / Signals Types
export interface ProfitTier {
  level: number;
  sizePct: number;
}

export interface Signal {
  symbol: string;
  action: "buy" | "sell" | "hold";
  confidence: number;
  sizeRecommendation: number;
  entryPrice: number;
  stopLoss: number;
  takeProfit: number;
  rationale: string;
  riskApproved: boolean;
  profitTiers: ProfitTier[];
  trailingStopPct: number;
}

export interface FactorScores {
  momentum: number;
  value: number;
  quality: number;
  volatility: number;
  liquidity: number;
  sentiment: number;
}

export interface StockPick {
  symbol: string;
  sector: string;
  theme: string;
  factorScores: FactorScores;
  finalScore: number;
  rank: number;
  rationale: string;
}

export interface PersonalizedStrategyResponse {
  userId: string;
  regime: MarketRegimeResponse;
  selectedSectors: string[];
  topThemes: string[];
  stockPicks: StockPick[];
  signals: Signal[];
  cachedAt: string;
  fromCache: boolean;
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
  aiReason?: string;
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
  userId: string;
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
// User Preferences
// ============================================================================

export type RiskProfile = "conservative" | "moderate" | "aggressive";

export interface UserPreferences {
  userId: string;
  riskProfile: RiskProfile;
  maxPortfolioRisk: string;
  maxPositionSize: string;
  preferredSectors: string[];
  excludedSectors: string[];
  enableNotifications: boolean;
  tradingEnabled: boolean;
}

// ============================================================================
// Broker Config Types
// ============================================================================

export interface BrokerConfig {
  apiKey: string;
  secretKey: string;
  paper: boolean;
}

export interface BrokerStatus {
  configured: boolean;
  connected: boolean;
  equity: number;
  cash: number;
  errorMessage: string;
}

export interface SyncResponse {
  success: boolean;
  positionsSynced: number;
  errorMessage: string;
}
