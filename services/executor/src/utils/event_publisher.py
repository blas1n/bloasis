"""Event publisher for Executor Service using Redpanda."""

import json
import logging
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer

from ..config import config

logger = logging.getLogger(__name__)


class EventPublisher:
    """Publishes execution events to Redpanda."""

    TOPIC_ORDER_EXECUTED = "order-executed"
    TOPIC_ORDER_CANCELLED = "order-cancelled"

    def __init__(self, producer: AIOKafkaProducer | None = None):
        """Initialize event publisher.

        Args:
            producer: Optional pre-configured producer (for testing)
        """
        self._producer = producer
        self._bootstrap_servers = config.redpanda_bootstrap_servers

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

    async def publish_order_executed(
        self,
        user_id: str,
        order_id: str,
        symbol: str,
        side: str,
        qty: float,
        status: str,
        filled_qty: float,
        filled_price: float,
    ) -> None:
        """Publish an order executed event.

        Args:
            user_id: User who placed the order
            order_id: Alpaca order ID
            symbol: Stock ticker symbol
            side: Order side (buy/sell)
            qty: Requested quantity
            status: Order status
            filled_qty: Quantity filled
            filled_price: Average fill price
        """
        if self._producer is None:
            logger.warning("Producer not connected, skipping event publish")
            return

        event = {
            "event_type": "order_executed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "status": status,
            "filled_qty": filled_qty,
            "filled_price": filled_price,
        }

        try:
            await self._producer.send_and_wait(
                self.TOPIC_ORDER_EXECUTED,
                value=event,
                key=user_id.encode("utf-8"),
            )
            logger.info(f"Published order executed event: {order_id}")
        except Exception as e:
            logger.error(f"Failed to publish order executed event: {e}")
            raise

    async def publish_order_cancelled(
        self,
        user_id: str,
        order_id: str,
    ) -> None:
        """Publish an order cancelled event.

        Args:
            user_id: User who cancelled the order
            order_id: Alpaca order ID
        """
        if self._producer is None:
            logger.warning("Producer not connected, skipping event publish")
            return

        event = {
            "event_type": "order_cancelled",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "order_id": order_id,
        }

        try:
            await self._producer.send_and_wait(
                self.TOPIC_ORDER_CANCELLED,
                value=event,
                key=user_id.encode("utf-8"),
            )
            logger.info(f"Published order cancelled event: {order_id}")
        except Exception as e:
            logger.error(f"Failed to publish order cancelled event: {e}")
            raise
