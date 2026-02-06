"""FinGPT Client for sentiment analysis."""

import logging
from typing import Any

import httpx

from ..config import config

logger = logging.getLogger(__name__)


class FinGPTClient:
    """Client for FinGPT sentiment analysis API.

    This client handles communication with the FinGPT external API
    for news sentiment analysis of stock symbols.

    Attributes:
        api_key: API key for authentication with FinGPT.
        base_url: Base URL for the FinGPT API.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        """Initialize FinGPT client.

        Args:
            api_key: Optional API key. Defaults to config.fingpt_api_key.
            base_url: Optional base URL. Defaults to config.fingpt_base_url.
        """
        self.api_key = api_key or config.fingpt_api_key
        self.base_url = base_url or config.fingpt_base_url
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Initialize HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
            logger.info(
                "FinGPT client connected",
                extra={"base_url": self.base_url},
            )

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("FinGPT client disconnected")

    async def analyze_sentiment(self, symbol: str) -> dict[str, Any]:
        """Analyze sentiment for a stock symbol.

        Calls the FinGPT API to get news sentiment analysis for the given symbol.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "MSFT").

        Returns:
            Dictionary containing sentiment analysis results:
            - sentiment: float from -1.0 (bearish) to 1.0 (bullish)
            - confidence: float from 0.0 to 1.0
            - news_count: int, number of news articles analyzed
            - summary: str, brief summary of sentiment

        Raises:
            No exceptions are raised. On error, returns default neutral sentiment.
        """
        if not self._client:
            await self.connect()

        try:
            response = await self._client.post(  # type: ignore[union-attr]
                "/v1/sentiment/analyze",
                json={"symbol": symbol},
            )
            response.raise_for_status()
            result = response.json()

            logger.debug(
                "FinGPT sentiment analysis completed",
                extra={
                    "symbol": symbol,
                    "sentiment": result.get("sentiment"),
                    "confidence": result.get("confidence"),
                },
            )
            return result

        except httpx.HTTPStatusError as e:
            logger.warning(
                "FinGPT API error",
                extra={
                    "symbol": symbol,
                    "status_code": e.response.status_code,
                    "error": str(e),
                },
            )
            return self._default_sentiment()

        except httpx.RequestError as e:
            logger.warning(
                "FinGPT request error",
                extra={"symbol": symbol, "error": str(e)},
            )
            return self._default_sentiment()

        except Exception as e:
            logger.warning(
                "FinGPT unexpected error",
                extra={"symbol": symbol, "error": str(e)},
            )
            return self._default_sentiment()

    def _default_sentiment(self) -> dict[str, Any]:
        """Return neutral sentiment as fallback.

        Returns:
            Dictionary with neutral sentiment values.
        """
        return {
            "sentiment": 0.0,
            "confidence": 0.0,
            "news_count": 0,
            "summary": "No sentiment data available",
        }
