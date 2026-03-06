"""Tests for background scheduler — periodic analysis for active users."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scheduler import (
    _run_analysis_cycle,
    scheduler_loop,
    start_scheduler,
    stop_scheduler,
)


@pytest.fixture
def mock_app():
    app = MagicMock()
    app.state.redis = AsyncMock()
    app.state.postgres = AsyncMock()
    app.state.llm = AsyncMock()
    return app


class TestRunAnalysisCycle:
    @patch("app.scheduler._get_active_users")
    async def test_runs_analysis_for_active_users(self, mock_get_active, mock_app):
        mock_get_active.return_value = ["user-1", "user-2"]

        mock_prefs = MagicMock()
        mock_prefs.risk_profile = "moderate"
        mock_prefs.excluded_sectors = []

        mock_user_repo = MagicMock()
        mock_user_repo.get_preferences = AsyncMock(return_value=mock_prefs)

        mock_strategy_svc = MagicMock()
        mock_strategy_svc.run_analysis = AsyncMock()

        with (
            patch("app.scheduler.UserRepository", return_value=mock_user_repo),
            patch("app.scheduler.MarketDataService"),
            patch("app.scheduler.MarketRegimeService"),
            patch("app.scheduler.ClassificationService"),
            patch("app.scheduler.StrategyService", return_value=mock_strategy_svc),
        ):
            await _run_analysis_cycle(mock_app)

        assert mock_strategy_svc.run_analysis.call_count == 2

    @patch("app.scheduler._get_active_users")
    async def test_skips_when_no_active_users(self, mock_get_active, mock_app):
        mock_get_active.return_value = []
        # Should not raise — early return
        with (
            patch("app.scheduler.UserRepository"),
            patch("app.scheduler.MarketDataService"),
            patch("app.scheduler.MarketRegimeService"),
            patch("app.scheduler.ClassificationService"),
            patch("app.scheduler.StrategyService"),
        ):
            await _run_analysis_cycle(mock_app)

    @patch("app.scheduler._get_active_users")
    async def test_isolates_per_user_errors(self, mock_get_active, mock_app):
        mock_get_active.return_value = ["user-fail", "user-ok"]

        mock_prefs = MagicMock()
        mock_prefs.risk_profile = "moderate"
        mock_prefs.excluded_sectors = []

        mock_user_repo = MagicMock()
        mock_user_repo.get_preferences = AsyncMock(return_value=mock_prefs)

        async def side_effect(**kwargs):
            if kwargs.get("user_id") == "user-fail":
                raise RuntimeError("LLM unavailable")

        mock_strategy_svc = MagicMock()
        mock_strategy_svc.run_analysis = AsyncMock(side_effect=side_effect)

        with (
            patch("app.scheduler.UserRepository", return_value=mock_user_repo),
            patch("app.scheduler.MarketDataService"),
            patch("app.scheduler.MarketRegimeService"),
            patch("app.scheduler.ClassificationService"),
            patch("app.scheduler.StrategyService", return_value=mock_strategy_svc),
        ):
            # Should not raise even though user-fail errors
            await _run_analysis_cycle(mock_app)

        # Both users attempted
        assert mock_strategy_svc.run_analysis.call_count == 2

    @patch("app.scheduler._get_active_users")
    async def test_uses_default_risk_profile_when_no_prefs(self, mock_get_active, mock_app):
        mock_get_active.return_value = ["user-1"]

        mock_user_repo = MagicMock()
        mock_user_repo.get_preferences = AsyncMock(return_value=None)

        mock_strategy_svc = MagicMock()
        mock_strategy_svc.run_analysis = AsyncMock()

        with (
            patch("app.scheduler.UserRepository", return_value=mock_user_repo),
            patch("app.scheduler.MarketDataService"),
            patch("app.scheduler.MarketRegimeService"),
            patch("app.scheduler.ClassificationService"),
            patch("app.scheduler.StrategyService", return_value=mock_strategy_svc),
        ):
            await _run_analysis_cycle(mock_app)

        call_kwargs = mock_strategy_svc.run_analysis.call_args.kwargs
        assert call_kwargs["risk_profile"] == "moderate"


class TestSchedulerLifecycle:
    async def test_start_and_stop(self, mock_app):
        await start_scheduler(mock_app)
        assert hasattr(mock_app.state, "scheduler_task")

        task = mock_app.state.scheduler_task
        assert not task.done()

        await stop_scheduler(mock_app)
        assert task.done()

    async def test_stop_without_start(self, mock_app):
        # Should not raise
        await stop_scheduler(mock_app)

    @patch("app.scheduler.settings")
    @patch("app.scheduler._run_analysis_cycle")
    async def test_loop_runs_at_interval(self, mock_cycle, mock_settings, mock_app):
        mock_settings.analysis_interval_seconds = 0.01  # Very short for test
        mock_cycle.return_value = None

        task = asyncio.create_task(scheduler_loop(mock_app))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert mock_cycle.call_count >= 1
