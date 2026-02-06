"""Redpanda event handlers for Notification Service."""

import logging
from typing import Any

from shared.utils.event_consumer import EventConsumer

from .websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class EventHandlers:
    """Handles events from Redpanda and routes to WebSocket clients.

    Consumes from 4 topics:
    - regime-events: Broadcast to all users
    - alert-events: Broadcast to all users
    - risk-events: Send to specific user
    - execution-events: Send to specific user
    """

    # Topics to consume
    TOPICS = [
        "regime-events",
        "alert-events",
        "risk-events",
        "execution-events",
    ]

    def __init__(self, ws_manager: WebSocketManager) -> None:
        """Initialize event handlers.

        Args:
            ws_manager: WebSocket manager for sending messages.
        """
        self.ws_manager = ws_manager
        self.consumer: EventConsumer | None = None

    async def start(
        self,
        brokers: str,
        group_id: str = "notification-service",
    ) -> None:
        """Start consuming events from Redpanda.

        Args:
            brokers: Redpanda broker addresses.
            group_id: Consumer group ID.
        """
        self.consumer = EventConsumer(
            brokers=brokers,
            group_id=group_id,
            topics=self.TOPICS,
        )

        # Register handlers for each event type
        self.consumer.register_handler("regime_change", self._handle_regime_change)
        self.consumer.register_handler("market_alert", self._handle_market_alert)
        self.consumer.register_handler("risk_alert", self._handle_risk_alert)
        self.consumer.register_handler("order_executed", self._handle_execution_event)

        await self.consumer.start()
        logger.info(
            "Event handlers started",
            extra={"topics": self.TOPICS, "group_id": group_id},
        )

    async def stop(self) -> None:
        """Stop consuming events."""
        if self.consumer:
            await self.consumer.stop()
            self.consumer = None
            logger.info("Event handlers stopped")

    async def _handle_regime_change(self, event: dict[str, Any]) -> None:
        """Handle regime change event - broadcast to all.

        Args:
            event: The regime change event data.
        """
        message = {
            "type": "regime_change",
            "data": event,
        }
        await self.ws_manager.broadcast(message)
        logger.debug(
            "Broadcasted regime change",
            extra={"new_regime": event.get("new_regime")},
        )

    async def _handle_market_alert(self, event: dict[str, Any]) -> None:
        """Handle market alert event - broadcast to all.

        Args:
            event: The market alert event data.
        """
        message = {
            "type": "market_alert",
            "data": event,
        }
        await self.ws_manager.broadcast(message)
        logger.debug(
            "Broadcasted market alert",
            extra={"alert_type": event.get("alert_type")},
        )

    async def _handle_risk_alert(self, event: dict[str, Any]) -> None:
        """Handle risk alert event - send to specific user.

        Args:
            event: The risk alert event data.
        """
        user_id = event.get("user_id")
        if not user_id:
            logger.warning("Risk alert missing user_id", extra={"event": event})
            return

        message = {
            "type": "risk_alert",
            "data": event,
        }
        sent = await self.ws_manager.send_to_user(user_id, message)
        if sent:
            logger.debug(
                "Sent risk alert to user",
                extra={"user_id": user_id, "alert_type": event.get("alert_type")},
            )

    async def _handle_execution_event(self, event: dict[str, Any]) -> None:
        """Handle execution event - send to specific user.

        Args:
            event: The execution event data.
        """
        user_id = event.get("user_id")
        if not user_id:
            logger.warning("Execution event missing user_id", extra={"event": event})
            return

        message = {
            "type": "order_executed",
            "data": event,
        }
        sent = await self.ws_manager.send_to_user(user_id, message)
        if sent:
            logger.debug(
                "Sent execution event to user",
                extra={
                    "user_id": user_id,
                    "order_id": event.get("order_id"),
                    "symbol": event.get("symbol"),
                },
            )

    @property
    def is_running(self) -> bool:
        """Check if event handlers are running.

        Returns:
            True if consumer is running, False otherwise.
        """
        return self.consumer is not None and self.consumer.is_running
