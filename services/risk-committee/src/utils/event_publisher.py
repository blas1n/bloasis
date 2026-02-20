"""Event publisher for Risk Committee Service using Redpanda."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from aiokafka import AIOKafkaProducer

from ..config import config

logger = logging.getLogger(__name__)


class EventPublisher:
    """Publishes risk decision events to Redpanda."""

    TOPIC_RISK_DECISIONS = "risk-decisions"

    def __init__(self, producer: AIOKafkaProducer | None = None):
        """Initialize event publisher.

        Args:
            producer: Optional pre-configured producer (for testing)
        """
        self._producer = producer
        self._bootstrap_servers = config.redpanda_brokers

    async def connect(self) -> None:
        """Connect to Redpanda."""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            logger.info(f"Connected to Redpanda at {self._bootstrap_servers}")

    async def close(self) -> None:
        """Close Redpanda connection."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            logger.info("Event publisher closed")

    async def publish_risk_decision(
        self,
        user_id: str,
        symbol: str,
        action: str,
        approved: bool,
        risk_score: float,
        reasoning: str,
    ) -> None:
        """Publish a risk decision event.

        Args:
            user_id: User who submitted the order
            symbol: Stock ticker symbol
            action: Order action (buy/sell)
            approved: Whether the order was approved
            risk_score: Overall risk score
            reasoning: Decision reasoning
        """
        if self._producer is None:
            logger.warning("Producer not connected, skipping event publish")
            return

        event = {
            "event_type": "risk_decision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "symbol": symbol,
            "action": action,
            "approved": approved,
            "risk_score": risk_score,
            "reasoning": reasoning,
        }

        try:
            await self._producer.send_and_wait(
                self.TOPIC_RISK_DECISIONS,
                value=event,
                key=user_id.encode("utf-8"),
            )
            logger.info(f"Published risk decision for {symbol}: approved={approved}")
        except Exception as e:
            logger.error(f"Failed to publish risk decision: {e}")
            raise

    async def publish_event(self, topic: str, event: dict[str, Any]) -> None:
        """Publish a generic event.

        Args:
            topic: Kafka topic name
            event: Event data
        """
        if self._producer is None:
            logger.warning("Producer not connected, skipping event publish")
            return

        try:
            await self._producer.send_and_wait(topic, value=event)
            logger.info(f"Published event to {topic}")
        except Exception as e:
            logger.error(f"Failed to publish event to {topic}: {e}")
            raise
