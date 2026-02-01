"""
Event publisher for Redpanda with priority support.

Provides typed event publishing for regime changes, market alerts,
strategy signals, and risk alerts with priority-based routing.
"""

import logging
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional
from uuid import uuid4

from .redpanda_client import RedpandaClient

logger = logging.getLogger(__name__)


class EventPriority(IntEnum):
    """Event priority levels for routing (matches events.proto)."""

    UNSPECIFIED = 0  # Default/unspecified (treated as LOW)
    LOW = 1  # Background tasks, analytics
    MEDIUM = 2  # Strategy updates, notifications
    HIGH = 3  # Regime changes, important signals
    CRITICAL = 4  # Crisis alerts, risk warnings


class EventPublisher:
    """
    Publishes typed events to Redpanda with priority routing.

    Uses partition keys based on priority to ensure ordered processing
    within each priority level.

    Example:
        publisher = EventPublisher(redpanda_client)
        await publisher.publish_regime_change(
            previous_regime="bull",
            new_regime="bear",
            confidence=0.85,
            reasoning="VIX spike detected",
        )
    """

    # Topic mapping for event types
    TOPIC_MAPPING = {
        "regime_change": "regime-events",
        "market_alert": "alert-events",
        "strategy_signal": "strategy-events",
        "risk_alert": "risk-events",
    }

    def __init__(self, redpanda_client: RedpandaClient) -> None:
        """
        Initialize event publisher.

        Args:
            redpanda_client: Connected RedpandaClient instance.
        """
        self.redpanda = redpanda_client

    async def publish_regime_change(
        self,
        previous_regime: str,
        new_regime: str,
        confidence: float,
        reasoning: str,
        priority: EventPriority = EventPriority.HIGH,
        metadata: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Publish regime change event.

        Args:
            previous_regime: Previous market regime.
            new_regime: New market regime.
            confidence: Classification confidence (0.0-1.0).
            reasoning: Explanation for the regime change.
            priority: Event priority (default: HIGH).
            metadata: Additional context.

        Returns:
            Event ID for tracking.
        """
        event_id = str(uuid4())
        event = {
            "event_id": event_id,
            "event_type": "regime_change",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "previous_regime": previous_regime,
            "new_regime": new_regime,
            "confidence": confidence,
            "reasoning": reasoning,
            "priority": priority.value,
            "metadata": metadata or {},
        }

        # Use priority-based partition key for ordered processing
        partition_key = f"priority-{priority.value}"

        await self.redpanda.publish(
            topic=self.TOPIC_MAPPING["regime_change"],
            message=event,
            partition_key=partition_key,
        )

        logger.info(
            "Published regime change event",
            extra={
                "event_id": event_id,
                "previous_regime": previous_regime,
                "new_regime": new_regime,
                "priority": priority.name,
            },
        )
        return event_id

    async def publish_market_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        priority: EventPriority = EventPriority.MEDIUM,
        indicators: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Publish market alert event.

        Args:
            alert_type: Type of alert (vix_spike, yield_curve_inversion, etc.).
            severity: Alert severity (info, warning, critical).
            message: Human-readable alert message.
            priority: Event priority (default: MEDIUM).
            indicators: Related indicator values.

        Returns:
            Event ID for tracking.
        """
        event_id = str(uuid4())
        event = {
            "event_id": event_id,
            "event_type": "market_alert",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
            "priority": priority.value,
            "indicators": indicators or {},
        }

        partition_key = f"priority-{priority.value}"

        await self.redpanda.publish(
            topic=self.TOPIC_MAPPING["market_alert"],
            message=event,
            partition_key=partition_key,
        )

        logger.info(
            "Published market alert",
            extra={
                "event_id": event_id,
                "alert_type": alert_type,
                "severity": severity,
                "priority": priority.name,
            },
        )
        return event_id

    async def publish_strategy_signal(
        self,
        strategy_id: str,
        signal_type: str,
        symbol: str,
        action: str,
        confidence: float,
        priority: EventPriority = EventPriority.HIGH,
        parameters: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Publish strategy signal event.

        Args:
            strategy_id: Strategy identifier.
            signal_type: Type of signal (entry, exit, adjust).
            symbol: Ticker symbol.
            action: Action (buy, sell, hold).
            confidence: Signal confidence (0.0-1.0).
            priority: Event priority (default: HIGH).
            parameters: Strategy-specific parameters.

        Returns:
            Event ID for tracking.
        """
        event_id = str(uuid4())
        event = {
            "event_id": event_id,
            "event_type": "strategy_signal",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy_id": strategy_id,
            "signal_type": signal_type,
            "symbol": symbol,
            "action": action,
            "confidence": confidence,
            "priority": priority.value,
            "parameters": parameters or {},
        }

        partition_key = f"priority-{priority.value}"

        await self.redpanda.publish(
            topic=self.TOPIC_MAPPING["strategy_signal"],
            message=event,
            partition_key=partition_key,
        )

        logger.info(
            "Published strategy signal",
            extra={
                "event_id": event_id,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "action": action,
                "priority": priority.name,
            },
        )
        return event_id

    async def publish_risk_alert(
        self,
        risk_type: str,
        severity: str,
        message: str,
        affected_portfolio: str = "",
        priority: EventPriority = EventPriority.HIGH,
        metrics: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Publish risk alert event.

        Args:
            risk_type: Type of risk (drawdown, correlation, exposure, black_swan).
            severity: Alert severity (warning, critical, emergency).
            message: Human-readable risk message.
            affected_portfolio: Portfolio ID if applicable.
            priority: Event priority (default: HIGH).
            metrics: Risk metrics.

        Returns:
            Event ID for tracking.
        """
        event_id = str(uuid4())
        event = {
            "event_id": event_id,
            "event_type": "risk_alert",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "risk_type": risk_type,
            "severity": severity,
            "message": message,
            "affected_portfolio": affected_portfolio,
            "priority": priority.value,
            "metrics": metrics or {},
        }

        partition_key = f"priority-{priority.value}"

        await self.redpanda.publish(
            topic=self.TOPIC_MAPPING["risk_alert"],
            message=event,
            partition_key=partition_key,
        )

        logger.info(
            "Published risk alert",
            extra={
                "event_id": event_id,
                "risk_type": risk_type,
                "severity": severity,
                "priority": priority.name,
            },
        )
        return event_id
