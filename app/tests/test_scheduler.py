"""Tests for background scheduler — periodic analysis and signal execution."""

import asyncio
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.models import (
    AnalysisResult,
    MarketRegime,
    OrderResult,
    OrderSide,
    OrderStatus,
    RiskProfile,
    SignalAction,
    TradingSignal,
)
from app.scheduler import (
    _execute_signals,
    _run_analysis_cycle,
    scheduler_loop,
    start_scheduler,
    stop_scheduler,
)


def _make_analysis_result(
    signals: list[TradingSignal] | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        user_id="test-user",
        regime=MarketRegime(
            regime="sideways",
            confidence=0.5,
            timestamp="2024-01-01",
            trigger="test",
        ),
        signals=signals or [],
    )


def _make_signal(
    symbol: str = "AAPL",
    action: SignalAction = SignalAction.BUY,
    confidence: float = 0.85,
    risk_approved: bool = True,
) -> TradingSignal:
    return TradingSignal(
        symbol=symbol,
        action=action,
        confidence=confidence,
        size_recommendation=Decimal("10"),
        entry_price=Decimal("150.00"),
        rationale="Test signal",
        risk_approved=risk_approved,
    )


@pytest.fixture
def mock_app():
    app = MagicMock()
    app.state.redis = AsyncMock()
    app.state.redis.get = AsyncMock(return_value=None)
    app.state.redis.setex = AsyncMock()
    app.state.postgres = AsyncMock()
    app.state.llm = AsyncMock()
    return app


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def mock_user_repo():
    return MagicMock()


class TestRunAnalysisCycle:
    @patch("app.scheduler._get_active_users")
    async def test_runs_analysis_for_active_users(self, mock_get_active, mock_app):
        mock_get_active.return_value = ["user-1", "user-2"]

        mock_prefs = MagicMock()
        mock_prefs.risk_profile = RiskProfile.MODERATE
        mock_prefs.excluded_sectors = []

        mock_user_repo = MagicMock()
        mock_user_repo.get_preferences = AsyncMock(return_value=mock_prefs)

        mock_strategy_svc = MagicMock()
        mock_strategy_svc.run_analysis = AsyncMock(return_value=_make_analysis_result())

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
        mock_prefs.risk_profile = RiskProfile.MODERATE
        mock_prefs.excluded_sectors = []

        mock_user_repo = MagicMock()
        mock_user_repo.get_preferences = AsyncMock(return_value=mock_prefs)

        async def side_effect(**kwargs):
            if kwargs.get("user_id") == "user-fail":
                raise RuntimeError("LLM unavailable")
            return _make_analysis_result()

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
        mock_strategy_svc.run_analysis = AsyncMock(return_value=_make_analysis_result())

        with (
            patch("app.scheduler.UserRepository", return_value=mock_user_repo),
            patch("app.scheduler.MarketDataService"),
            patch("app.scheduler.MarketRegimeService"),
            patch("app.scheduler.ClassificationService"),
            patch("app.scheduler.StrategyService", return_value=mock_strategy_svc),
        ):
            await _run_analysis_cycle(mock_app)

        call_kwargs = mock_strategy_svc.run_analysis.call_args.kwargs
        assert call_kwargs["risk_profile"] == RiskProfile.MODERATE

    @patch("app.scheduler._execute_signals")
    @patch("app.scheduler._get_active_users")
    async def test_executes_signals_after_analysis(self, mock_get_active, mock_execute, mock_app):
        uid = uuid.uuid4()
        mock_get_active.return_value = [uid]
        mock_execute.return_value = 1

        signals = [_make_signal()]
        mock_prefs = MagicMock()
        mock_prefs.risk_profile = RiskProfile.MODERATE
        mock_prefs.excluded_sectors = []

        mock_user_repo = MagicMock()
        mock_user_repo.get_preferences = AsyncMock(return_value=mock_prefs)

        mock_strategy_svc = MagicMock()
        mock_strategy_svc.run_analysis = AsyncMock(
            return_value=_make_analysis_result(signals=signals)
        )

        with (
            patch("app.scheduler.UserRepository", return_value=mock_user_repo),
            patch("app.scheduler.MarketDataService"),
            patch("app.scheduler.MarketRegimeService"),
            patch("app.scheduler.ClassificationService"),
            patch("app.scheduler.StrategyService", return_value=mock_strategy_svc),
        ):
            await _run_analysis_cycle(mock_app)

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert call_args[0][1] == uid
        assert len(call_args[0][2]) == 1


class TestExecuteSignals:
    async def test_filters_hold_signals(self, mock_app, user_id, mock_user_repo):
        signals = [_make_signal(action=SignalAction.HOLD, confidence=0.9)]
        result = await _execute_signals(mock_app, user_id, signals, mock_user_repo)
        assert result == 0

    async def test_filters_low_confidence(self, mock_app, user_id, mock_user_repo):
        signals = [_make_signal(confidence=0.3)]
        result = await _execute_signals(mock_app, user_id, signals, mock_user_repo)
        assert result == 0

    async def test_filters_risk_not_approved(self, mock_app, user_id, mock_user_repo):
        signals = [_make_signal(risk_approved=False)]
        result = await _execute_signals(mock_app, user_id, signals, mock_user_repo)
        assert result == 0

    async def test_deduplicates_already_executed(self, mock_app, user_id, mock_user_repo):
        mock_app.state.redis.get = AsyncMock(return_value="1")  # Already executed
        signals = [_make_signal()]
        result = await _execute_signals(mock_app, user_id, signals, mock_user_repo)
        assert result == 0

    @patch("app.scheduler._build_executor_service")
    async def test_skips_when_no_broker(self, mock_build, mock_app, user_id, mock_user_repo):
        mock_build.return_value = None
        signals = [_make_signal()]
        result = await _execute_signals(mock_app, user_id, signals, mock_user_repo)
        assert result == 0

    @patch("app.scheduler._build_executor_service")
    async def test_happy_path_executes_order(self, mock_build, mock_app, user_id, mock_user_repo):
        mock_executor = AsyncMock()
        mock_executor.execute_order = AsyncMock(
            return_value=OrderResult(
                order_id="broker-123",
                symbol="AAPL",
                side=OrderSide.BUY,
                qty=Decimal("10"),
                status=OrderStatus.FILLED,
            )
        )
        mock_build.return_value = mock_executor
        signals = [_make_signal(symbol="AAPL")]

        result = await _execute_signals(mock_app, user_id, signals, mock_user_repo)

        assert result == 1
        mock_executor.execute_order.assert_called_once()
        call_kwargs = mock_executor.execute_order.call_args.kwargs
        assert call_kwargs["symbol"] == "AAPL"
        assert call_kwargs["side"] == "buy"
        assert call_kwargs["qty"] == Decimal("10")

    @patch("app.scheduler._build_executor_service")
    async def test_marks_dedup_key_after_execution(
        self, mock_build, mock_app, user_id, mock_user_repo
    ):
        mock_executor = AsyncMock()
        mock_executor.execute_order = AsyncMock(
            return_value=OrderResult(
                order_id="broker-123",
                symbol="AAPL",
                side=OrderSide.BUY,
                qty=Decimal("10"),
                status=OrderStatus.FILLED,
            )
        )
        mock_build.return_value = mock_executor
        signals = [_make_signal(symbol="AAPL")]

        await _execute_signals(mock_app, user_id, signals, mock_user_repo)

        # Verify dedup key was set
        mock_app.state.redis.setex.assert_called()
        dedup_call = mock_app.state.redis.setex.call_args
        assert f"executed_signal:{user_id}:AAPL:buy" == dedup_call[0][0]

    @patch("app.scheduler._build_executor_service")
    async def test_failed_order_still_sets_dedup(
        self, mock_build, mock_app, user_id, mock_user_repo
    ):
        mock_executor = AsyncMock()
        mock_executor.execute_order = AsyncMock(
            return_value=OrderResult(
                order_id="",
                symbol="AAPL",
                side=OrderSide.BUY,
                qty=Decimal("10"),
                status=OrderStatus.FAILED,
                error_message="Risk rejected",
            )
        )
        mock_build.return_value = mock_executor
        signals = [_make_signal()]

        result = await _execute_signals(mock_app, user_id, signals, mock_user_repo)

        assert result == 0  # Failed order not counted
        mock_app.state.redis.setex.assert_called()  # But dedup key still set

    @patch("app.scheduler._build_executor_service")
    async def test_executor_exception_isolated(self, mock_build, mock_app, user_id, mock_user_repo):
        mock_executor = AsyncMock()
        mock_executor.execute_order = AsyncMock(side_effect=Exception("Broker timeout"))
        mock_build.return_value = mock_executor
        signals = [_make_signal(symbol="AAPL"), _make_signal(symbol="MSFT")]

        # Should not raise — errors are isolated per signal
        result = await _execute_signals(mock_app, user_id, signals, mock_user_repo)
        assert result == 0
        assert mock_executor.execute_order.call_count == 2


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
