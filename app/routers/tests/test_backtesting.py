"""Tests for backtesting router — /v1/backtesting/*."""

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.backtesting.models import (
    BacktestResult,
    PortfolioMetrics,
    SymbolResult,
)
from app.dependencies import get_backtesting_service, get_current_user
from app.main import create_app

USER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def mock_backtesting_svc():
    return AsyncMock()


@pytest.fixture
def app(mock_backtesting_svc):
    application = create_app()
    application.dependency_overrides[get_current_user] = lambda: USER_UUID
    application.dependency_overrides[get_backtesting_service] = lambda: mock_backtesting_svc
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _make_backtest_result(**overrides) -> BacktestResult:
    defaults = {
        "backtest_id": "backtest_abc123",
        "results": [SymbolResult(symbol="AAPL", total_return=0.15, sharpe_ratio=1.2, passed=True)],
        "portfolio_metrics": PortfolioMetrics(
            total_return=0.15, sharpe_ratio=1.2, max_drawdown=-0.05
        ),
        "created_at": "2025-01-01T00:00:00+00:00",
        "strategy_type": "ma_crossover",
    }
    defaults.update(overrides)
    return BacktestResult(**defaults)


class TestRunBacktest:
    def test_success(self, client, mock_backtesting_svc):
        mock_backtesting_svc.run_backtest.return_value = _make_backtest_result()
        resp = client.post(
            "/v1/backtesting/run",
            json={"symbols": ["AAPL"], "strategyType": "ma_crossover"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["backtestId"] == "backtest_abc123"
        assert len(data["results"]) == 1
        mock_backtesting_svc.run_backtest.assert_awaited_once()

    def test_success_with_all_options(self, client, mock_backtesting_svc):
        mock_backtesting_svc.run_backtest.return_value = _make_backtest_result()
        resp = client.post(
            "/v1/backtesting/run",
            json={
                "symbols": ["AAPL", "MSFT"],
                "strategyType": "rsi",
                "period": "3mo",
                "initialCash": "50000",
                "commission": 0.002,
                "slippage": 0.005,
                "stopLoss": 0.05,
                "takeProfit": 0.1,
            },
        )
        assert resp.status_code == 200

    def test_invalid_symbol_special_chars(self, client):
        resp = client.post(
            "/v1/backtesting/run",
            json={"symbols": ["A@PL"], "strategyType": "ma_crossover"},
        )
        assert resp.status_code == 422

    def test_invalid_strategy_type(self, client):
        resp = client.post(
            "/v1/backtesting/run",
            json={"symbols": ["AAPL"], "strategyType": "invalid"},
        )
        assert resp.status_code == 422

    def test_invalid_period(self, client):
        resp = client.post(
            "/v1/backtesting/run",
            json={"symbols": ["AAPL"], "strategyType": "ma_crossover", "period": "10y"},
        )
        assert resp.status_code == 422

    def test_empty_symbols(self, client):
        resp = client.post(
            "/v1/backtesting/run",
            json={"symbols": [], "strategyType": "ma_crossover"},
        )
        assert resp.status_code == 422

    def test_value_error_returns_400(self, client, mock_backtesting_svc):
        mock_backtesting_svc.run_backtest.side_effect = ValueError("No data for symbol")
        resp = client.post(
            "/v1/backtesting/run",
            json={"symbols": ["AAPL"], "strategyType": "ma_crossover"},
        )
        assert resp.status_code == 400
        assert "No data for symbol" in resp.json()["detail"]

    def test_symbol_normalization(self, client, mock_backtesting_svc):
        mock_backtesting_svc.run_backtest.return_value = _make_backtest_result()
        resp = client.post(
            "/v1/backtesting/run",
            json={"symbols": ["aapl"], "strategyType": "ma_crossover"},
        )
        assert resp.status_code == 200
        call_kwargs = mock_backtesting_svc.run_backtest.call_args.kwargs
        assert call_kwargs["symbols"] == ["AAPL"]


class TestGetBacktestResults:
    def test_found(self, client, mock_backtesting_svc):
        mock_backtesting_svc.get_results.return_value = _make_backtest_result()
        resp = client.get("/v1/backtesting/results/backtest_abc123")
        assert resp.status_code == 200
        assert resp.json()["backtestId"] == "backtest_abc123"

    def test_not_found(self, client, mock_backtesting_svc):
        mock_backtesting_svc.get_results.return_value = None
        resp = client.get("/v1/backtesting/results/nonexistent")
        assert resp.status_code == 404


class TestCompareStrategies:
    def test_success(self, client, mock_backtesting_svc):
        mock_backtesting_svc.compare_strategies.return_value = {
            "comparisons": [
                {"backtest_id": "bt1", "strategy_name": "ma_crossover", "rank": 1},
                {"backtest_id": "bt2", "strategy_name": "rsi", "rank": 2},
            ],
            "best_strategy_id": "bt1",
        }
        resp = client.post(
            "/v1/backtesting/compare",
            json={"backtestIds": ["bt1", "bt2"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["bestStrategyId"] == "bt1"
        assert len(data["comparisons"]) == 2

    def test_value_error_returns_400(self, client, mock_backtesting_svc):
        mock_backtesting_svc.compare_strategies.side_effect = ValueError("No valid backtests found")
        resp = client.post(
            "/v1/backtesting/compare",
            json={"backtestIds": ["bt1", "bt2"]},
        )
        assert resp.status_code == 400

    def test_requires_min_two_ids(self, client):
        resp = client.post(
            "/v1/backtesting/compare",
            json={"backtestIds": ["only_one"]},
        )
        assert resp.status_code == 422
