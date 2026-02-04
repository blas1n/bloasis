"""Layer 2: Technical Analyst using Claude.

The Technical Analyst performs sophisticated technical analysis using Claude's
complex reasoning capabilities to synthesize multiple factors and indicators.
"""

import logging
from decimal import Decimal
from typing import Any

from shared.ai_clients import ClaudeClient

from ..clients.market_data_client import MarketDataClient
from ..prompts import format_technical_prompt, get_technical_model_parameters
from ..workflow.state import MarketContext, TechnicalSignal

logger = logging.getLogger(__name__)


class TechnicalAnalyst:
    """Layer 2: Claude-based technical analysis.

    Performs sophisticated technical analysis with multi-factor synthesis
    using Claude's complex reasoning capabilities.
    """

    def __init__(
        self,
        claude_client: ClaudeClient,
        market_data_client: MarketDataClient,
    ):
        """Initialize Technical Analyst.

        Args:
            claude_client: Claude client instance
            market_data_client: Market Data client instance
        """
        self.claude = claude_client
        self.market_data = market_data_client

    async def analyze(
        self,
        stock_picks: list[dict],
        market_context: MarketContext,
    ) -> list[TechnicalSignal]:
        """Perform technical analysis on stock picks.

        Args:
            stock_picks: Stock picks from Stage 3 (Factor Scoring)
            market_context: Macro economic context from Layer 1

        Returns:
            List of technical signals with recommendations
        """
        logger.info(f"Starting technical analysis for {len(stock_picks)} stocks")

        # Fetch OHLCV data for all symbols
        ohlcv_data = await self._fetch_ohlcv_data(stock_picks)

        # Prepare data for Claude
        stock_data = self._prepare_stock_data(stock_picks)
        market_context_dict = {
            "regime": market_context.regime,
            "risk_level": market_context.risk_level,
            "sector_outlook": market_context.sector_outlook,
        }

        try:
            # Format OHLCV data for prompt
            ohlcv_summary = self._format_ohlcv_summary(ohlcv_data)

            # Get formatted prompt from YAML
            system_prompt, user_prompt = format_technical_prompt(
                stock_data=stock_data,
                ohlcv_summary=ohlcv_summary,
                market_context=market_context_dict,
            )

            # Get model parameters from YAML
            model_params = get_technical_model_parameters()

            # Call Claude for technical analysis using generic analyze method
            response = await self.claude.analyze(
                prompt=user_prompt,
                system_prompt=system_prompt,
                response_format="json",
                max_tokens=model_params.get("max_tokens", 8000),
            )

            # Convert response to TechnicalSignal objects
            signals = []
            if not isinstance(response, list):
                logger.error(f"Expected list response, got {type(response)}")
                return []

            signal_list: list[dict[str, Any]] = response
            for signal_data in signal_list:
                try:
                    signal = TechnicalSignal(
                        symbol=signal_data["symbol"],
                        direction=signal_data["direction"],
                        strength=float(signal_data["strength"]),
                        entry_price=Decimal(str(signal_data["entry_price"])),
                        indicators=signal_data.get("indicators", {}),
                        rationale=signal_data.get("rationale", ""),
                    )
                    signals.append(signal)
                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(
                        f"Failed to parse signal for {signal_data.get('symbol', 'unknown')}: {e}"
                    )
                    continue

            logger.info(
                f"Technical analysis complete: {len(signals)} signals generated"
            )
            return signals

        except Exception as e:
            logger.error(f"Technical analysis failed: {e}", exc_info=True)
            return []

    async def _fetch_ohlcv_data(self, stock_picks: list[dict]) -> dict:
        """Fetch OHLCV data for all stocks.

        Args:
            stock_picks: Stock picks list

        Returns:
            Dictionary of symbol -> OHLCV bars
        """
        ohlcv_data = {}

        for pick in stock_picks:
            symbol = pick["symbol"]
            try:
                # Fetch 60 days of OHLCV data
                bars = await self.market_data.get_ohlcv(symbol, period="60d")
                ohlcv_data[symbol] = bars
            except Exception as e:
                logger.warning(f"Failed to fetch OHLCV data for {symbol}: {e}")
                ohlcv_data[symbol] = []

        return ohlcv_data

    def _prepare_stock_data(self, stock_picks: list[dict]) -> list[dict]:
        """Prepare stock data for Claude analysis.

        Args:
            stock_picks: Stock picks from Stage 3

        Returns:
            Formatted stock data list
        """
        stock_data = []

        for pick in stock_picks:
            stock_data.append(
                {
                    "symbol": pick["symbol"],
                    "sector": pick["sector"],
                    "theme": pick.get("theme", ""),
                    "final_score": pick.get("final_score", 0),
                    "factor_scores": pick.get("factor_scores", {}),
                }
            )

        return stock_data

    def _format_ohlcv_summary(self, ohlcv_data: dict) -> str:
        """Format OHLCV data for prompt.

        Args:
            ohlcv_data: Dictionary of symbol -> OHLCV bars

        Returns:
            Formatted string summary
        """
        lines = []
        for symbol, bars in ohlcv_data.items():
            if bars and len(bars) > 0:
                latest = bars[-1]
                # Calculate 20-day average if enough data
                if len(bars) >= 20:
                    avg_20d = sum(b["close"] for b in bars[-20:]) / 20
                else:
                    avg_20d = latest["close"]

                lines.append(
                    f"{symbol}: Last={latest['close']:.2f}, "
                    f"Vol={latest['volume']:,}, "
                    f"20d_avg={avg_20d:.2f}"
                )
            else:
                lines.append(f"{symbol}: No data available")

        return "\n".join(lines) if lines else "No OHLCV data available"
