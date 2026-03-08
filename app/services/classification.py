"""Classification Service — Sector/Theme filtering with cache.

Replaces: services/classification/ (440 lines gRPC → ~80 lines direct)
Stage 1: Sector filter (11 GICS → 3-7)
Stage 2: Theme ranking → candidate symbols
"""

import json
import logging
from typing import Any

from shared.ai_clients.llm_client import LLMClient
from shared.utils.redis_client import RedisClient

from ..config import settings
from ..core.models import CandidateSymbol
from ..core.prompts.sector import SECTOR_SYSTEM_PROMPT, format_sector_prompt

logger = logging.getLogger(__name__)


class ClassificationService:
    """Sector/theme classification with Tier 1 shared caching."""

    def __init__(self, redis: RedisClient, llm: LLMClient) -> None:
        self.redis = redis
        self.llm = llm

    async def get_candidates(self, regime: str) -> list[CandidateSymbol]:
        """Get candidate symbols for the current regime.

        Args:
            regime: Current market regime.

        Returns:
            List of candidate symbols with sectors and preliminary scores.
        """
        cache_key = f"candidates:{regime}"
        cached = await self.redis.get(cache_key)
        if cached and isinstance(cached, list):
            return [CandidateSymbol(**c) for c in cached]

        candidates = await self._classify(regime)

        await self.redis.setex(
            cache_key,
            settings.cache_sector_ttl,
            [c.model_dump() for c in candidates],
        )

        return candidates

    async def _classify(self, regime: str) -> list[CandidateSymbol]:
        """Run sector/theme classification via Claude."""
        prompt = format_sector_prompt([], regime, settings.gics_sectors)

        try:
            result = await self.llm.analyze(
                prompt=prompt,
                system_prompt=SECTOR_SYSTEM_PROMPT,
                response_format="json",
                max_tokens=2000,
            )

            return self._parse_candidates(result, regime)

        except (RuntimeError, json.JSONDecodeError, ValueError):
            logger.error("Classification failed", exc_info=True)
            return self._fallback_candidates()

    def _parse_candidates(self, data: dict[str, Any], regime: str) -> list[CandidateSymbol]:
        """Parse LLM response into candidate symbols."""
        candidates = []
        if isinstance(data, dict) and "candidates" in data:
            for c in data["candidates"]:
                candidates.append(
                    CandidateSymbol(
                        symbol=c.get("symbol", ""),
                        sector=c.get("sector", "Unknown"),
                        theme=c.get("theme", ""),
                        preliminary_score=c.get("score", 50.0),
                    )
                )

        if not candidates:
            return self._fallback_candidates()

        return candidates[:50]  # Cap at 50

    def _fallback_candidates(self) -> list[CandidateSymbol]:
        """Default candidates when classification fails."""
        return [
            CandidateSymbol(symbol=s, sector=sec, theme="Core", preliminary_score=50.0)
            for s, sec in settings.fallback_candidates
        ]
