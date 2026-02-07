"""
Prometheus metrics utilities for BLOASIS services.

Provides standardized metrics collection across all gRPC services
with support for request tracking, trading operations, and portfolio monitoring.

Usage:
    from shared.utils.metrics import (
        track_grpc_call,
        record_trading_signal,
        record_order_executed,
        update_portfolio_value,
        get_metrics,
        start_metrics_server,
    )

    # Track gRPC calls with decorator
    @track_grpc_call(service="market-regime", method="GetCurrentRegime")
    async def get_current_regime(self, request, context):
        ...

    # Record trading operations
    record_trading_signal("buy", "AAPL")
    record_order_executed("buy", "AAPL", success=True)
    update_portfolio_value("user-123", 150000.50)

    # Start metrics HTTP server
    start_metrics_server(port=9100)
"""

import functools
import time
from typing import Any, Callable, Optional, TypeVar

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)

# Type variable for generic decorator
F = TypeVar("F", bound=Callable[..., Any])

# =============================================================================
# Metric Definitions
# =============================================================================

# gRPC request metrics
grpc_requests_total = Counter(
    "grpc_requests_total",
    "Total number of gRPC requests",
    ["service", "method", "status"],
)

grpc_request_duration_seconds = Histogram(
    "grpc_request_duration_seconds",
    "gRPC request duration in seconds",
    ["service", "method"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Trading signal metrics
trading_signals_generated_total = Counter(
    "trading_signals_generated_total",
    "Total number of trading signals generated",
    ["signal_type", "symbol"],
)

# Order execution metrics
orders_executed_total = Counter(
    "orders_executed_total",
    "Total number of orders executed",
    ["order_type", "symbol", "status"],
)

# Portfolio metrics
portfolio_value_total = Gauge(
    "portfolio_value_total",
    "Current portfolio value in USD",
    ["user_id"],
)

# Risk committee metrics
risk_committee_decisions_total = Counter(
    "risk_committee_decisions_total",
    "Total number of risk committee decisions",
    ["decision"],
)

# Market regime metrics
market_regime_current = Gauge(
    "market_regime_current",
    "Current market regime (encoded as label)",
    ["regime"],
)

market_regime_confidence = Gauge(
    "market_regime_confidence",
    "Confidence of current market regime classification",
    [],
)


# =============================================================================
# Decorator for gRPC Call Tracking
# =============================================================================


def track_grpc_call(service: str, method: str) -> Callable[[F], F]:
    """
    Decorator to track gRPC call metrics.

    Automatically records request count, duration, and status for gRPC methods.
    Works with both sync and async functions.

    Args:
        service: Name of the service (e.g., "market-regime", "strategy")
        method: Name of the gRPC method (e.g., "GetCurrentRegime")

    Returns:
        Decorated function with metrics tracking

    Example:
        @track_grpc_call(service="market-regime", method="GetCurrentRegime")
        async def GetCurrentRegime(self, request, context):
            return RegimeResponse(regime="bull")
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise e
            finally:
                duration = time.perf_counter() - start_time
                grpc_requests_total.labels(
                    service=service, method=method, status=status
                ).inc()
                grpc_request_duration_seconds.labels(
                    service=service, method=method
                ).observe(duration)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise e
            finally:
                duration = time.perf_counter() - start_time
                grpc_requests_total.labels(
                    service=service, method=method, status=status
                ).inc()
                grpc_request_duration_seconds.labels(
                    service=service, method=method
                ).observe(duration)

        # Check if the function is async
        if _is_coroutine_function(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _is_coroutine_function(func: Callable[..., Any]) -> bool:
    """Check if a function is a coroutine function."""
    import asyncio
    import inspect

    return asyncio.iscoroutinefunction(func) or inspect.iscoroutinefunction(func)


# =============================================================================
# Trading Signal Recording
# =============================================================================


def record_trading_signal(signal_type: str, symbol: str) -> None:
    """
    Record a trading signal generation.

    Args:
        signal_type: Type of signal (e.g., "buy", "sell", "hold")
        symbol: Stock symbol (e.g., "AAPL", "GOOGL")

    Example:
        record_trading_signal("buy", "AAPL")
    """
    trading_signals_generated_total.labels(
        signal_type=signal_type, symbol=symbol
    ).inc()


# =============================================================================
# Order Execution Recording
# =============================================================================


def record_order_executed(
    order_type: str,
    symbol: str,
    success: bool = True,
) -> None:
    """
    Record an order execution.

    Args:
        order_type: Type of order (e.g., "buy", "sell")
        symbol: Stock symbol (e.g., "AAPL", "GOOGL")
        success: Whether the order was successfully executed

    Example:
        record_order_executed("buy", "AAPL", success=True)
    """
    status = "success" if success else "failed"
    orders_executed_total.labels(
        order_type=order_type, symbol=symbol, status=status
    ).inc()


# =============================================================================
# Portfolio Value Tracking
# =============================================================================


def update_portfolio_value(user_id: str, value: float) -> None:
    """
    Update the current portfolio value for a user.

    Args:
        user_id: Unique identifier for the user
        value: Current portfolio value in USD

    Example:
        update_portfolio_value("user-123", 150000.50)
    """
    portfolio_value_total.labels(user_id=user_id).set(value)


# =============================================================================
# Risk Committee Decision Recording
# =============================================================================


def record_risk_decision(decision: str) -> None:
    """
    Record a risk committee decision.

    Args:
        decision: Decision type (e.g., "approved", "rejected", "modified")

    Example:
        record_risk_decision("approved")
    """
    risk_committee_decisions_total.labels(decision=decision).inc()


# =============================================================================
# Market Regime Tracking
# =============================================================================


def update_market_regime(regime: str, confidence: float) -> None:
    """
    Update the current market regime classification.

    Args:
        regime: Current regime (e.g., "bull", "bear", "crisis", "sideways", "recovery")
        confidence: Confidence level of the classification (0.0 to 1.0)

    Example:
        update_market_regime("bull", 0.92)
    """
    # Reset all regime labels and set the current one
    for r in ["bull", "bear", "crisis", "sideways", "recovery"]:
        market_regime_current.labels(regime=r).set(0)
    market_regime_current.labels(regime=regime).set(1)
    market_regime_confidence.set(confidence)


# =============================================================================
# Metrics Export
# =============================================================================


def get_metrics(registry: Optional[CollectorRegistry] = None) -> bytes:
    """
    Get current metrics in Prometheus exposition format.

    Args:
        registry: Optional custom registry. Uses default if not provided.

    Returns:
        Metrics data as bytes in Prometheus text format

    Example:
        metrics_data = get_metrics()
        # Returns: b'# HELP grpc_requests_total Total number of gRPC requests...'
    """
    if registry is None:
        registry = REGISTRY
    return generate_latest(registry)


def start_metrics_server(port: int = 9100, addr: str = "") -> None:
    """
    Start an HTTP server to expose metrics.

    Starts a background thread that serves metrics at /metrics endpoint.
    This is the standard way to expose metrics for Prometheus scraping.

    Args:
        port: Port to listen on (default: 9100)
        addr: Address to bind to (default: all interfaces)

    Example:
        # Start metrics server on port 9100
        start_metrics_server(port=9100)
        # Prometheus can now scrape http://localhost:9100/metrics
    """
    start_http_server(port=port, addr=addr)


# =============================================================================
# Custom Metrics Creation
# =============================================================================


def create_counter(
    name: str,
    description: str,
    labels: Optional[list[str]] = None,
) -> Counter:
    """
    Create a custom Counter metric.

    Args:
        name: Metric name (should follow Prometheus naming conventions)
        description: Human-readable description of the metric
        labels: Optional list of label names

    Returns:
        Prometheus Counter instance

    Example:
        api_calls = create_counter(
            "api_calls_total",
            "Total API calls",
            ["endpoint", "method"]
        )
        api_calls.labels(endpoint="/users", method="GET").inc()
    """
    return Counter(name, description, labels or [])


def create_histogram(
    name: str,
    description: str,
    labels: Optional[list[str]] = None,
    buckets: Optional[tuple[float, ...]] = None,
) -> Histogram:
    """
    Create a custom Histogram metric.

    Args:
        name: Metric name (should follow Prometheus naming conventions)
        description: Human-readable description of the metric
        labels: Optional list of label names
        buckets: Optional custom bucket boundaries

    Returns:
        Prometheus Histogram instance

    Example:
        response_time = create_histogram(
            "response_time_seconds",
            "Response time in seconds",
            ["endpoint"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0)
        )
        response_time.labels(endpoint="/users").observe(0.25)
    """
    if buckets is None:
        buckets = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    return Histogram(name, description, labels or [], buckets=buckets)


def create_gauge(
    name: str,
    description: str,
    labels: Optional[list[str]] = None,
) -> Gauge:
    """
    Create a custom Gauge metric.

    Args:
        name: Metric name (should follow Prometheus naming conventions)
        description: Human-readable description of the metric
        labels: Optional list of label names

    Returns:
        Prometheus Gauge instance

    Example:
        active_connections = create_gauge(
            "active_connections",
            "Number of active connections",
            ["service"]
        )
        active_connections.labels(service="api").set(42)
    """
    return Gauge(name, description, labels or [])
