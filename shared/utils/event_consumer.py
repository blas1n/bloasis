"""
Event consumer for Redpanda with priority handling.

Provides async event consumption with handler registration
and priority-based filtering.
"""

import asyncio
import json
import logging
import os
from typing import Any, Callable, Coroutine, Optional

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

logger = logging.getLogger(__name__)

# Type alias for async event handlers
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventConsumer:
    """
    Async Redpanda consumer with priority handling.

    Supports registering handlers for specific event types with
    minimum priority filtering.

    Example:
        consumer = EventConsumer(
            group_id="risk-committee",
            topics=["regime-events", "alert-events"],
        )

        async def handle_regime_change(event: dict) -> None:
            print(f"Regime changed to {event['new_regime']}")

        consumer.register_handler(
            event_type="regime_change",
            handler=handle_regime_change,
            min_priority=2,  # Only HIGH and CRITICAL
        )

        await consumer.start()
    """

    def __init__(
        self,
        group_id: str,
        topics: list[str],
        brokers: Optional[str] = None,
        auto_offset_reset: str = "earliest",
    ) -> None:
        """
        Initialize event consumer.

        Args:
            group_id: Consumer group ID for load balancing.
            topics: List of topics to subscribe to.
            brokers: Broker addresses (default: REDPANDA_BROKERS env var).
            auto_offset_reset: Where to start consuming (earliest/latest).
        """
        self.brokers = brokers or os.getenv("REDPANDA_BROKERS", "redpanda:9092")
        self.group_id = group_id
        self.topics = topics
        self.auto_offset_reset = auto_offset_reset

        self._consumer: Optional[AIOKafkaConsumer] = None
        self._handlers: dict[str, tuple[EventHandler, int]] = {}
        self._running = False
        self._consume_task: Optional[asyncio.Task[None]] = None

    def register_handler(
        self,
        event_type: str,
        handler: EventHandler,
        min_priority: int = 0,
    ) -> None:
        """
        Register handler for an event type.

        Args:
            event_type: Event type to handle (e.g., "regime_change").
            handler: Async function to call when event is received.
            min_priority: Minimum priority level to process (0-3).
        """
        self._handlers[event_type] = (handler, min_priority)
        logger.info(
            "Registered event handler",
            extra={
                "event_type": event_type,
                "min_priority": min_priority,
            },
        )

    def unregister_handler(self, event_type: str) -> None:
        """
        Unregister handler for an event type.

        Args:
            event_type: Event type to unregister.
        """
        if event_type in self._handlers:
            del self._handlers[event_type]
            logger.info(
                "Unregistered event handler",
                extra={"event_type": event_type},
            )

    async def start(self) -> None:
        """
        Start consuming events.

        Creates consumer, subscribes to topics, and starts
        the consumption loop in a background task.
        """
        if self._running:
            logger.warning("Consumer already running")
            return

        try:
            self._consumer = AIOKafkaConsumer(
                *self.topics,
                bootstrap_servers=self.brokers,
                group_id=self.group_id,
                auto_offset_reset=self.auto_offset_reset,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                enable_auto_commit=True,
            )
            await self._consumer.start()
            self._running = True

            logger.info(
                "Event consumer started",
                extra={
                    "group_id": self.group_id,
                    "topics": self.topics,
                    "brokers": self.brokers,
                },
            )

            # Start consumption loop in background
            self._consume_task = asyncio.create_task(self._consume_loop())

        except KafkaError as e:
            logger.error(
                "Failed to start consumer",
                extra={"error": str(e)},
            )
            raise ConnectionError(f"Failed to start consumer: {e}") from e

    async def stop(self) -> None:
        """
        Stop consuming events.

        Cancels the consumption loop and closes the consumer.
        """
        self._running = False

        if self._consume_task:
            task = self._consume_task
            self._consume_task = None
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._consumer:
            await self._consumer.stop()
            self._consumer = None

        logger.info(
            "Event consumer stopped",
            extra={"group_id": self.group_id},
        )

    async def _consume_loop(self) -> None:
        """Main consumption loop."""
        if not self._consumer:
            return

        while self._running:
            try:
                async for msg in self._consumer:
                    if not self._running:
                        break
                    if msg.value is not None:
                        await self._handle_message(msg.value)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Consumer loop error",
                    extra={"error": str(e)},
                )
                # Brief pause before retrying
                await asyncio.sleep(1)

    async def _handle_message(self, event: dict[str, Any]) -> None:
        """
        Handle incoming event message.

        Routes event to registered handler if priority meets threshold.

        Args:
            event: Deserialized event dictionary.
        """
        event_type = event.get("event_type")
        priority = event.get("priority", 0)
        event_id = event.get("event_id", "unknown")

        if event_type not in self._handlers:
            logger.debug(
                "No handler for event type",
                extra={"event_type": event_type, "event_id": event_id},
            )
            return

        handler, min_priority = self._handlers[event_type]

        if priority < min_priority:
            logger.debug(
                "Event priority below threshold",
                extra={
                    "event_type": event_type,
                    "event_id": event_id,
                    "priority": priority,
                    "min_priority": min_priority,
                },
            )
            return

        try:
            await handler(event)
            logger.info(
                "Event handled successfully",
                extra={
                    "event_type": event_type,
                    "event_id": event_id,
                    "priority": priority,
                },
            )
        except Exception as e:
            logger.error(
                "Handler error",
                extra={
                    "event_type": event_type,
                    "event_id": event_id,
                    "error": str(e),
                },
            )

    @property
    def is_running(self) -> bool:
        """Check if consumer is running."""
        return self._running
