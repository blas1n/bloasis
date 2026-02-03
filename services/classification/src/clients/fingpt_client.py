"""FinGPT client for sector and thematic analysis.

Provides both real Hugging Face API client and mock client for development.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import List

import httpx

from ..config import config
from ..models import SectorScore, ThemeScore
from ..prompts import (
    format_sector_prompt,
    format_theme_prompt,
    get_sector_model_parameters,
    get_sector_response_schema,
    get_theme_model_parameters,
    get_theme_response_schema,
)

logger = logging.getLogger(__name__)

# All 11 GICS sectors
ALL_SECTORS = [
    "Technology",
    "Healthcare",
    "Financials",
    "Consumer Discretionary",
    "Industrials",
    "Communication Services",
    "Consumer Staples",
    "Energy",
    "Utilities",
    "Real Estate",
    "Materials",
]


class FinGPTClientBase(ABC):
    """Base class for FinGPT clients."""

    @abstractmethod
    async def analyze_sectors(self, regime: str) -> List[SectorScore]:
        """Analyze sectors based on market regime.

        Args:
            regime: Market regime ("crisis", "bear", "bull", "sideways", "recovery")

        Returns:
            List of sector scores (all 11 GICS sectors)
        """
        pass

    @abstractmethod
    async def analyze_themes(self, sectors: List[str], regime: str) -> List[ThemeScore]:
        """Analyze investment themes within selected sectors.

        Args:
            sectors: Selected sectors from Stage 1
            regime: Market regime for context

        Returns:
            List of theme scores ranked by relevance
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close client connections."""
        pass


class FinGPTClient(FinGPTClientBase):
    """Real FinGPT client using Hugging Face Inference API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ):
        """Initialize FinGPT client.

        Args:
            api_key: Hugging Face API token
            model: Model ID (default from config)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or config.huggingface_token
        self.model = model or config.fingpt_model
        self.timeout = timeout

        if not self.api_key:
            raise ValueError("Hugging Face API token required for FinGPT client")

        self.client = httpx.AsyncClient(
            base_url="https://api-inference.huggingface.co",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        logger.info(f"FinGPT client initialized (model: {self.model})")

    async def analyze_sectors(self, regime: str) -> List[SectorScore]:
        """Analyze sectors using FinGPT with YAML prompts and structured output."""
        # Get prompt and schema from YAML
        prompt = format_sector_prompt(regime=regime)
        schema = get_sector_response_schema()
        params = get_sector_model_parameters()

        try:
            response = await self.client.post(
                f"/models/{self.model}",
                json={
                    "inputs": prompt,
                    "parameters": {
                        **params,
                        "grammar": {"type": "json", "value": schema},  # Structured output
                    },
                },
            )
            response.raise_for_status()

            result = response.json()
            generated_text = result[0]["generated_text"] if isinstance(result, list) else result

            # Parse JSON response
            sectors_data = self._parse_json_response(generated_text)
            return self._convert_to_sector_scores(sectors_data)

        except Exception as e:
            logger.error(f"FinGPT sector analysis failed: {e}")
            raise

    async def analyze_themes(self, sectors: List[str], regime: str) -> List[ThemeScore]:
        """Analyze themes using FinGPT with YAML prompts and structured output."""
        # Get prompt and schema from YAML
        prompt = format_theme_prompt(sectors=sectors, regime=regime)
        schema = get_theme_response_schema()
        params = get_theme_model_parameters()

        try:
            response = await self.client.post(
                f"/models/{self.model}",
                json={
                    "inputs": prompt,
                    "parameters": {
                        **params,
                        "grammar": {"type": "json", "value": schema},  # Structured output
                    },
                },
            )
            response.raise_for_status()

            result = response.json()
            generated_text = result[0]["generated_text"] if isinstance(result, list) else result

            # Parse JSON response
            themes_data = self._parse_json_response(generated_text)
            return self._convert_to_theme_scores(themes_data)

        except Exception as e:
            logger.error(f"FinGPT theme analysis failed: {e}")
            raise

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from generated text."""
        # Find JSON in text (may have extra text before/after)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = text[start:end]
            return json.loads(json_str)
        raise ValueError(f"No valid JSON found in response: {text}")

    def _convert_to_sector_scores(self, data: dict) -> List[SectorScore]:
        """Convert dict to SectorScore models."""
        sectors = data.get("sectors", [])
        return [
            SectorScore(
                sector=s["sector"],
                score=float(s["score"]),
                rationale=s["rationale"],
                selected=s.get("selected", False),
            )
            for s in sectors
        ]

    def _convert_to_theme_scores(self, data: dict) -> List[ThemeScore]:
        """Convert dict to ThemeScore models."""
        themes = data.get("themes", [])
        return [
            ThemeScore(
                theme=t["theme"],
                sector=t["sector"],
                score=float(t["score"]),
                rationale=t["rationale"],
                representative_symbols=t.get("representative_symbols", []),
            )
            for t in themes
        ]

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
        logger.info("FinGPT client closed")


class MockFinGPTClient(FinGPTClientBase):
    """Mock FinGPT client for development and testing.

    Uses rule-based logic to generate realistic sector and theme analysis.
    """

    def __init__(self):
        """Initialize mock client."""
        logger.info("MockFinGPT client initialized (no API calls)")

    async def analyze_sectors(self, regime: str) -> List[SectorScore]:
        """Generate mock sector analysis based on regime."""
        # Rule-based sector selection by regime
        sector_strategies = {
            "bull": {
                "selected": ["Technology", "Consumer Discretionary", "Communication Services"],
                "scores": {
                    "Technology": 90,
                    "Consumer Discretionary": 85,
                    "Communication Services": 82,
                    "Healthcare": 70,
                    "Financials": 68,
                    "Industrials": 65,
                    "Materials": 62,
                    "Consumer Staples": 55,
                    "Energy": 50,
                    "Utilities": 45,
                    "Real Estate": 48,
                },
            },
            "bear": {
                "selected": ["Consumer Staples", "Healthcare", "Utilities"],
                "scores": {
                    "Consumer Staples": 88,
                    "Healthcare": 85,
                    "Utilities": 80,
                    "Real Estate": 60,
                    "Energy": 55,
                    "Technology": 45,
                    "Financials": 42,
                    "Consumer Discretionary": 38,
                    "Communication Services": 40,
                    "Industrials": 35,
                    "Materials": 32,
                },
            },
            "crisis": {
                "selected": ["Utilities", "Consumer Staples", "Healthcare"],
                "scores": {
                    "Utilities": 92,
                    "Consumer Staples": 90,
                    "Healthcare": 88,
                    "Real Estate": 50,
                    "Technology": 35,
                    "Energy": 30,
                    "Financials": 25,
                    "Consumer Discretionary": 20,
                    "Communication Services": 30,
                    "Industrials": 22,
                    "Materials": 18,
                },
            },
            "sideways": {
                "selected": ["Healthcare", "Consumer Staples", "Technology", "Utilities"],
                "scores": {
                    "Healthcare": 78,
                    "Consumer Staples": 75,
                    "Technology": 72,
                    "Utilities": 70,
                    "Financials": 65,
                    "Communication Services": 63,
                    "Real Estate": 60,
                    "Energy": 58,
                    "Industrials": 55,
                    "Consumer Discretionary": 52,
                    "Materials": 50,
                },
            },
            "recovery": {
                "selected": [
                    "Technology",
                    "Financials",
                    "Industrials",
                    "Consumer Discretionary",
                ],
                "scores": {
                    "Technology": 88,
                    "Financials": 85,
                    "Industrials": 82,
                    "Consumer Discretionary": 80,
                    "Materials": 75,
                    "Energy": 72,
                    "Healthcare": 68,
                    "Communication Services": 70,
                    "Consumer Staples": 60,
                    "Real Estate": 65,
                    "Utilities": 55,
                },
            },
        }

        strategy = sector_strategies.get(regime, sector_strategies["sideways"])
        selected_sectors = set(strategy["selected"])

        return [
            SectorScore(
                sector=sector,
                score=float(strategy["scores"][sector]),
                rationale=f"Mock analysis for {sector} in {regime} regime",
                selected=(sector in selected_sectors),
            )
            for sector in ALL_SECTORS
        ]

    async def analyze_themes(self, sectors: List[str], regime: str) -> List[ThemeScore]:
        """Generate mock thematic analysis."""
        # Mock themes by sector
        theme_database = {
            "Technology": [
                ("AI Infrastructure", ["NVDA", "AMD", "TSM"], 92),
                ("Cloud Computing", ["MSFT", "GOOGL", "AMZN"], 88),
                ("Cybersecurity", ["CRWD", "PANW", "ZS"], 85),
                ("Software SaaS", ["CRM", "NOW", "WDAY"], 82),
            ],
            "Healthcare": [
                ("Biotech Innovation", ["MRNA", "REGN", "VRTX"], 90),
                ("Medical Devices", ["ISRG", "EW", "SYK"], 85),
                ("Pharmaceuticals", ["LLY", "NVO", "JNJ"], 80),
            ],
            "Financials": [
                ("Digital Banking", ["JPM", "BAC", "V"], 88),
                ("Payment Systems", ["MA", "V", "PYPL"], 85),
                ("Fintech", ["SQ", "SOFI", "COIN"], 80),
            ],
            "Consumer Discretionary": [
                ("E-Commerce", ["AMZN", "SHOP", "MELI"], 90),
                ("Electric Vehicles", ["TSLA", "RIVN", "LCID"], 85),
                ("Streaming Services", ["NFLX", "DIS", "SPOT"], 80),
            ],
            "Consumer Staples": [
                ("Food & Beverage", ["KO", "PEP", "MDLZ"], 85),
                ("Household Products", ["PG", "CL", "KMB"], 82),
            ],
            "Energy": [
                ("Clean Energy", ["ENPH", "SEDG", "RUN"], 88),
                ("Oil & Gas", ["XOM", "CVX", "COP"], 75),
            ],
            "Utilities": [
                ("Renewable Utilities", ["NEE", "DUK", "SO"], 85),
                ("Electric Utilities", ["AEP", "EXC", "D"], 80),
            ],
            "Industrials": [
                ("Aerospace & Defense", ["BA", "LMT", "RTX"], 85),
                ("Industrial Automation", ["ROK", "EMR", "ITW"], 82),
            ],
            "Materials": [
                ("Rare Earth Minerals", ["MP", "ALB", "LAC"], 85),
                ("Chemicals", ["LIN", "ECL", "SHW"], 78),
            ],
            "Communication Services": [
                ("Social Media", ["META", "SNAP", "PINS"], 85),
                ("Telecom 5G", ["TMUS", "VZ", "T"], 75),
            ],
            "Real Estate": [
                ("Data Center REITs", ["EQIX", "DLR", "CCI"], 88),
                ("Residential REITs", ["AVB", "EQR", "MAA"], 75),
            ],
        }

        themes = []
        for sector in sectors:
            sector_themes = theme_database.get(sector, [])
            for theme_name, symbols, base_score in sector_themes:
                # Adjust score slightly based on regime
                score_adjustment = {"bull": 5, "bear": -5, "crisis": -10, "recovery": 3}.get(
                    regime, 0
                )
                adjusted_score = max(0, min(100, base_score + score_adjustment))

                themes.append(
                    ThemeScore(
                        theme=theme_name,
                        sector=sector,
                        score=adjusted_score,
                        rationale=f"Mock analysis for {theme_name} in {regime} regime",
                        representative_symbols=symbols,
                    )
                )

        # Sort by score descending
        themes.sort(key=lambda t: t.score, reverse=True)
        return themes

    async def close(self) -> None:
        """No-op for mock client."""
        logger.info("MockFinGPT client closed (no resources to cleanup)")
