"""Unit tests for Classification Service business logic.

Tests Stage 1 (Sector Filter), Stage 2 (Thematic Filter), and combined pipeline.
All external dependencies (Redis, Market Regime Service, Claude) are mocked.
"""

import pytest

from src.models import SectorScore, ThemeScore


@pytest.mark.asyncio
class TestSectorAnalysis:
    """Test Stage 1: Sector Filter."""

    async def test_sector_analysis_calls_claude(self, classification_service, mock_cache, mock_analyst):
        """Should call Claude analyst and parse response."""
        mock_cache.get.return_value = None

        sectors, cached_at = await classification_service.get_sector_analysis("bull")

        mock_analyst.analyze.assert_called_once()
        assert len(sectors) > 0
        assert all(isinstance(s, SectorScore) for s in sectors)
        assert sectors[0].score >= sectors[-1].score  # Sorted descending

    async def test_sector_analysis_cache_hit(self, classification_service, mock_cache, mock_analyst):
        """Cache hit should skip Claude and return cached data."""
        cached_data = {
            "sectors": [
                {
                    "sector": "Technology",
                    "score": 90.0,
                    "rationale": "Test",
                    "selected": True,
                }
            ],
            "cached_at": "2026-02-02T12:00:00Z",
        }
        mock_cache.get.return_value = cached_data

        sectors, cached_at = await classification_service.get_sector_analysis("bull")

        mock_analyst.analyze.assert_not_called()
        assert len(sectors) == 1
        assert sectors[0].sector == "Technology"
        assert cached_at == "2026-02-02T12:00:00Z"

    async def test_sector_analysis_force_refresh_bypasses_cache(
        self, classification_service, mock_cache, mock_analyst
    ):
        """force_refresh=True should skip cache read and call Claude."""
        mock_cache.get.return_value = {"sectors": [], "cached_at": "old"}

        await classification_service.get_sector_analysis("bull", force_refresh=True)

        mock_cache.get.assert_not_called()
        mock_analyst.analyze.assert_called_once()
        mock_cache.set.assert_called_once()

    async def test_sector_analysis_result_written_to_cache(
        self, classification_service, mock_cache
    ):
        """Cache miss should write result back to cache."""
        mock_cache.get.return_value = None

        await classification_service.get_sector_analysis("bull")

        mock_cache.set.assert_called_once()

    async def test_sector_analysis_claude_failure_propagates(
        self, classification_service, mock_cache, mock_analyst
    ):
        """Claude failure should propagate (no silent fallback)."""
        mock_cache.get.return_value = None
        mock_analyst.analyze.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await classification_service.get_sector_analysis("bull")


@pytest.mark.asyncio
class TestThematicAnalysis:
    """Test Stage 2: Thematic Filter."""

    async def test_thematic_analysis_calls_claude(
        self, classification_service, mock_cache, mock_analyst
    ):
        """Should call Claude analyst and return parsed themes."""
        mock_cache.get.return_value = None
        sectors = ["Technology", "Healthcare"]

        themes, cached_at = await classification_service.get_thematic_analysis(sectors, "bull")

        mock_analyst.analyze.assert_called_once()
        assert len(themes) > 0
        assert all(isinstance(t, ThemeScore) for t in themes)
        assert themes[0].score >= themes[-1].score  # Sorted descending

    async def test_thematic_analysis_cache_hit(
        self, classification_service, mock_cache, mock_analyst
    ):
        """Cache hit should skip Claude."""
        cached_data = {
            "themes": [
                {
                    "theme": "AI Infrastructure",
                    "sector": "Technology",
                    "score": 92.0,
                    "rationale": "Test",
                    "representative_symbols": ["NVDA", "AMD"],
                }
            ],
            "cached_at": "2026-02-02T12:00:00Z",
        }
        mock_cache.get.return_value = cached_data

        themes, cached_at = await classification_service.get_thematic_analysis(
            ["Technology"], "bull"
        )

        mock_analyst.analyze.assert_not_called()
        assert len(themes) == 1
        assert themes[0].theme == "AI Infrastructure"
        assert "NVDA" in themes[0].representative_symbols

    async def test_thematic_analysis_representative_symbols(
        self, classification_service, mock_cache
    ):
        """Parsed themes should include representative symbols."""
        mock_cache.get.return_value = None

        themes, _ = await classification_service.get_thematic_analysis(["Technology"], "bull")

        assert all(len(t.representative_symbols) > 0 for t in themes)

    async def test_thematic_analysis_claude_failure_propagates(
        self, classification_service, mock_cache, mock_analyst
    ):
        """Claude failure should propagate (no silent fallback)."""
        mock_cache.get.return_value = None
        mock_analyst.analyze.side_effect = Exception("API error")

        with pytest.raises(Exception, match="API error"):
            await classification_service.get_thematic_analysis(["Technology"], "bull")


@pytest.mark.asyncio
class TestCandidateSymbols:
    """Test Stage 1+2 combined pipeline."""

    async def test_candidate_symbols_full_pipeline(
        self, classification_service, mock_cache, mock_regime_client
    ):
        """Full pipeline should return candidates with required fields."""
        mock_cache.get.return_value = None

        candidates, selected_sectors, top_themes, regime = (
            await classification_service.get_candidate_symbols()
        )

        assert regime == "bull"  # From mock regime client
        assert len(selected_sectors) > 0
        assert len(top_themes) > 0
        assert len(candidates) > 0
        assert len(candidates) <= 50

        for candidate in candidates:
            assert candidate.symbol
            assert candidate.sector in selected_sectors
            assert candidate.theme
            assert 0 <= candidate.preliminary_score <= 100

    async def test_candidate_symbols_with_explicit_regime(
        self, classification_service, mock_cache
    ):
        """Explicit regime should skip regime service call."""
        mock_cache.get.return_value = None

        candidates, selected_sectors, top_themes, regime = (
            await classification_service.get_candidate_symbols(regime="bull")
        )

        assert regime == "bull"
        assert len(candidates) > 0

    async def test_candidate_symbols_max_candidates(self, classification_service, mock_cache):
        """max_candidates limit should be respected."""
        mock_cache.get.return_value = None

        candidates, _, _, _ = await classification_service.get_candidate_symbols(
            regime="bull", max_candidates=2
        )

        assert len(candidates) <= 2

    async def test_candidate_symbols_cache_hit(self, classification_service, mock_cache, mock_analyst):
        """Cache hit should skip full pipeline."""
        cached_data = {
            "candidates": [
                {
                    "symbol": "AAPL",
                    "sector": "Technology",
                    "theme": "AI Infrastructure",
                    "preliminary_score": 92.0,
                }
            ],
            "selected_sectors": ["Technology"],
            "top_themes": ["AI Infrastructure"],
            "regime": "bull",
        }
        mock_cache.get.return_value = cached_data

        candidates, selected_sectors, top_themes, regime = (
            await classification_service.get_candidate_symbols(regime="bull")
        )

        mock_analyst.analyze.assert_not_called()
        assert len(candidates) == 1
        assert candidates[0].symbol == "AAPL"
        assert regime == "bull"


@pytest.mark.asyncio
class TestCaching:
    """Test caching behavior."""

    async def test_cache_key_consistency(self, classification_service, mock_cache):
        """Same inputs should produce same cache key."""
        mock_cache.get.return_value = None

        await classification_service.get_sector_analysis("bull")
        await classification_service.get_sector_analysis("bull")

        assert mock_cache.get.call_count == 2
        assert (
            mock_cache.get.call_args_list[0][0][0]
            == mock_cache.get.call_args_list[1][0][0]
        )

    async def test_cache_key_different_for_different_regimes(
        self, classification_service, mock_cache
    ):
        """Different regimes should use different cache keys."""
        mock_cache.get.return_value = None

        await classification_service.get_sector_analysis("bull")
        await classification_service.get_sector_analysis("bear")

        key1 = mock_cache.get.call_args_list[0][0][0]
        key2 = mock_cache.get.call_args_list[1][0][0]
        assert key1 != key2
