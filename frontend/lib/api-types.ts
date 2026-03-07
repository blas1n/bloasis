/**
 * Re-exported types from the generated OpenAPI schema.
 *
 * The backend returns camelCase JSON via CamelJSONResponse, but the generated
 * OpenAPI types use snake_case field names. This module provides camelCase
 * type aliases that match the actual runtime shape of API responses.
 *
 * For request bodies (which use Pydantic aliases), the generated types already
 * have camelCase field names and can be used directly.
 */

import type { components } from "./generated/api-types";

// ---------------------------------------------------------------------------
// Utility: recursively convert snake_case keys to camelCase
// ---------------------------------------------------------------------------
type CamelCase<S extends string> = S extends `${infer P}_${infer R}`
  ? `${P}${Capitalize<CamelCase<R>>}`
  : S;

type CamelCaseKeys<T> = T extends readonly (infer U)[]
  ? CamelCaseKeys<U>[]
  : T extends object
    ? { [K in keyof T as K extends string ? CamelCase<K> : K]: CamelCaseKeys<T[K]> }
    : T;

// ---------------------------------------------------------------------------
// Schema types — camelCase versions of generated response schemas
// ---------------------------------------------------------------------------
export type PortfolioSummary = CamelCaseKeys<components["schemas"]["PortfolioSummaryResponse"]>;
export type Position = CamelCaseKeys<components["schemas"]["Position"]>;
export type PositionsResponse = CamelCaseKeys<components["schemas"]["PositionsResponse"]>;
export type MarketRegime = CamelCaseKeys<components["schemas"]["MarketRegime"]>;
export type MarketRegimeIndicators = CamelCaseKeys<components["schemas"]["MarketRegimeIndicators"]>;
export type Signal = CamelCaseKeys<components["schemas"]["TradingSignal"]>;
export type StockPick = CamelCaseKeys<components["schemas"]["StockPick"]>;
export type FactorScores = CamelCaseKeys<components["schemas"]["FactorScores"]>;
export type ProfitTier = CamelCaseKeys<components["schemas"]["ProfitTier"]>;
export type AnalysisResult = CamelCaseKeys<components["schemas"]["AnalysisResult"]>;
export type Trade = CamelCaseKeys<components["schemas"]["Trade"]>;
export type TradeHistoryResponse = CamelCaseKeys<components["schemas"]["TradeHistoryResponse"]>;
export type TradingStatus = CamelCaseKeys<components["schemas"]["TradingStatusResponse"]>;
export type TradingControlResponse = CamelCaseKeys<components["schemas"]["TradingControlResponse"]>;
export type UserPreferences = CamelCaseKeys<components["schemas"]["UserPreferences"]>;
export type BrokerStatus = CamelCaseKeys<components["schemas"]["BrokerStatusResponse"]>;
export type BrokerUpdateResponse = CamelCaseKeys<components["schemas"]["BrokerUpdateResponse"]>;
export type SyncResponse = CamelCaseKeys<components["schemas"]["SyncResponse"]>;

// Enum-like types (already simple strings, no key conversion needed)
export type RegimeType = components["schemas"]["RegimeType"];
export type RiskLevel = components["schemas"]["RiskLevel"];
export type RiskProfile = components["schemas"]["RiskProfile"];
export type SignalAction = components["schemas"]["SignalAction"];
export type OrderSide = components["schemas"]["OrderSide"];
