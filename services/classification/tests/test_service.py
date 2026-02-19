"""Unit tests for Classification Service business logic.

Tests Stage 1 (Sector Filter), Stage 2 (Thematic Filter), and combined pipeline.
"""

import pytest

from src.models import SectorScore, ThemeScore


@pytest.mark.asyncio
class TestSectorAnalysis:
    """Test Stage 1: Sector Filter."""

    async def test_sector_analysis_cache_miss(self, classification_service, mock_cache):
        """Test sector analysis with cache miss."""
        # Setup: cache miss
        mock_cache.get.return_value = None

        # Execute
        sectors, cached_at = await classification_service.get_sector_analysis("bull")

        # Verify
        assert len(sectors) == 11  # All 11 GICS sectors
        assert all(isinstance(s, SectorScore) for s in sectors)
        assert any(s.selected for s in sectors)  # At least some sectors selected
        assert sectors[0].score >= sectors[-1].score  # Sorted by score descending

        # Verify cache was called
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_called_once()

    async def test_sector_analysis_cache_hit(self, classification_service, mock_cache):
        """Test sector analysis with cache hit."""
        # Setup: cache hit
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

        # Execute
        sectors, cached_at = await classification_service.get_sector_analysis("bull")

        # Verify
        assert len(sectors) == 1
        assert sectors[0].sector == "Technology"
        assert cached_at == "2026-02-02T12:00:00Z"

        # Cache should be read but not written
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_not_called()

    async def test_sector_analysis_force_refresh(self, classification_service, mock_cache):
        """Test sector analysis with force_refresh bypasses cache."""
        # Setup: cache would hit, but force_refresh=True
        mock_cache.get.return_value = {"sectors": [], "cached_at": "old"}

        # Execute
        sectors, cached_at = await classification_service.get_sector_analysis(
            "bull", force_refresh=True
        )

        # Verify: should skip cache read
        mock_cache.get.assert_not_called()
        mock_cache.set.assert_called_once()  # But still writes to cache

    async def test_sector_analysis_different_regimes(self, classification_service, mock_cache):
        """Test that different regimes produce different results."""
        mock_cache.get.return_value = None

        # Bull regime
        sectors_bull, _ = await classification_service.get_sector_analysis("bull")
        selected_bull = [s.sector for s in sectors_bull if s.selected]

        # Crisis regime
        sectors_crisis, _ = await classification_service.get_sector_analysis("crisis")
        selected_crisis = [s.sector for s in sectors_crisis if s.selected]

        # Verify different selections
        assert set(selected_bull) != set(selected_crisis)
        # Bull should favor growth sectors
        assert "Technology" in selected_bull
        # Crisis should favor defensive sectors
        assert "Utilities" in selected_crisis or "Consumer Staples" in selected_crisis


@pytest.mark.asyncio
class TestThematicAnalysis:
    """Test Stage 2: Thematic Filter."""

    async def test_thematic_analysis_cache_miss(self, classification_service, mock_cache):
        """Test thematic analysis with cache miss."""
        # Setup
        mock_cache.get.return_value = None
        sectors = ["Technology", "Healthcare"]

        # Execute
        themes, cached_at = await classification_service.get_thematic_analysis(sectors, "bull")

        # Verify
        assert len(themes) > 0
        assert all(isinstance(t, ThemeScore) for t in themes)
        assert all(t.sector in sectors for t in themes)
        assert themes[0].score >= themes[-1].score  # Sorted by score

        # Verify cache
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_called_once()

    async def test_thematic_analysis_cache_hit(self, classification_service, mock_cache):
        """Test thematic analysis with cache hit."""
        # Setup: cache hit
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

        # Execute
        themes, cached_at = await classification_service.get_thematic_analysis(
            ["Technology"], "bull"
        )

        # Verify
        assert len(themes) == 1
        assert themes[0].theme == "AI Infrastructure"
        assert "NVDA" in themes[0].representative_symbols

    async def test_thematic_analysis_representative_symbols(
        self, classification_service, mock_cache
    ):
        """Test that themes include representative symbols."""
        mock_cache.get.return_value = None

        themes, _ = await classification_service.get_thematic_analysis(["Technology"], "bull")

        # Verify all themes have representative symbols
        assert all(len(t.representative_symbols) > 0 for t in themes)


@pytest.mark.asyncio
class TestCandidateSymbols:
    """Test Stage 1+2 combined pipeline."""

    async def test_candidate_symbols_full_pipeline(
        self, classification_service, mock_cache, mock_regime_client
    ):
        """Test full pipeline from regime to candidates."""
        # Setup: no cache
        mock_cache.get.return_value = None

        # Execute (no regime provided - should fetch from service)
        (
            candidates,
            selected_sectors,
            top_themes,
            regime,
        ) = await classification_service.get_candidate_symbols()

        # Verify
        assert regime == "bull"  # From mock regime client
        assert len(selected_sectors) > 0
        assert len(top_themes) > 0
        assert len(candidates) > 0
        assert len(candidates) <= 50  # Default max

        # Verify candidates have all required fields
        for candidate in candidates:
            assert candidate.symbol
            assert candidate.sector in selected_sectors
            assert candidate.theme
            assert 0 <= candidate.preliminary_score <= 100

    async def test_candidate_symbols_with_regime(self, classification_service, mock_cache):
        """Test candidate symbols with explicit regime."""
        mock_cache.get.return_value = None

        # Execute with explicit regime
        (
            candidates,
            selected_sectors,
            top_themes,
            regime,
        ) = await classification_service.get_candidate_symbols(regime="crisis")

        # Verify
        assert regime == "crisis"
        assert len(candidates) > 0

        # Crisis regime should select defensive sectors
        defensive_sectors = {"Utilities", "Consumer Staples", "Healthcare"}
        assert any(s in defensive_sectors for s in selected_sectors)

    async def test_candidate_symbols_max_candidates(self, classification_service, mock_cache):
        """Test that max_candidates limit is respected."""
        mock_cache.get.return_value = None

        # Request only 10 candidates
        candidates, _, _, _ = await classification_service.get_candidate_symbols(
            regime="bull", max_candidates=10
        )

        # Verify
        assert len(candidates) <= 10

    async def test_candidate_symbols_cache_hit(self, classification_service, mock_cache):
        """Test candidate symbols with cache hit."""
        # Setup: cache hit
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

        # Execute
        (
            candidates,
            selected_sectors,
            top_themes,
            regime,
        ) = await classification_service.get_candidate_symbols(regime="bull")

        # Verify
        assert len(candidates) == 1
        assert candidates[0].symbol == "AAPL"
        assert regime == "bull"

    async def test_candidate_symbols_no_selected_sectors_fallback(
        self, classification_service, mock_cache
    ):
        """Test fallback when no sectors are selected."""
        from unittest.mock import patch

        mock_cache.get.return_value = None

        # Patch _fallback_sector_analysis to return all sectors as not selected
        original_fallback = classification_service._fallback_sector_analysis

        def mock_no_selection(regime):
            sectors = original_fallback(regime)
            for s in sectors:
                s.selected = False
            return sectors

        with patch.object(classification_service, "_fallback_sector_analysis", mock_no_selection):
            # Execute
            candidates, selected_sectors, _, _ = (
                await classification_service.get_candidate_symbols(regime="bull")
            )

        # Verify: should fallback to top 3 sectors
        assert len(selected_sectors) == 3
        assert len(candidates) > 0


@pytest.mark.asyncio
class TestCaching:
    """Test caching behavior."""

    async def test_cache_key_consistency(self, classification_service, mock_cache):
        """Test that same inputs produce same cache keys."""
        mock_cache.get.return_value = None

        # Call twice with same parameters
        await classification_service.get_sector_analysis("bull")
        await classification_service.get_sector_analysis("bull")

        # Verify cache was checked with same key both times
        assert mock_cache.get.call_count == 2
        call_args_1 = mock_cache.get.call_args_list[0][0][0]
        call_args_2 = mock_cache.get.call_args_list[1][0][0]
        assert call_args_1 == call_args_2

    async def test_cache_key_different_for_different_regimes(
        self, classification_service, mock_cache
    ):
        """Test that different regimes use different cache keys."""
        mock_cache.get.return_value = None

        await classification_service.get_sector_analysis("bull")
        await classification_service.get_sector_analysis("bear")

        # Verify different cache keys
        call_args_1 = mock_cache.get.call_args_list[0][0][0]
        call_args_2 = mock_cache.get.call_args_list[1][0][0]
        assert call_args_1 != call_args_2
