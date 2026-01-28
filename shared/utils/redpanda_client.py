"""
Redpanda client utility for BLOASIS services.

Provides async event publishing to Redpanda using the Kafka API.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

logger = logging.getLogger(__name__)


class RedpandaClient:
    """
    Async Redpanda client for event publishing.

    Uses environment variables for configuration:
    - REDPANDA_BROKERS: Comma-separated broker addresses (default: 'redpanda:9092')

    Example:
        client = RedpandaClient()
        await client.start()
        await client.publish("regime-change", {"regime": "crisis", "confidence": 0.95})
        await client.stop()
    """

    def __init__(self, brokers: Optional[str] = None) -> None:
        """
        Initialize Redpanda client configuration.

        Args:
            brokers: Comma-separated broker addresses.
                     Defaults to REDPANDA_BROKERS env var or 'redpanda:9092'.
        """
        self.brokers: str = brokers if brokers is not None else (
            os.getenv("REDPANDA_BROKERS") or "redpanda:9092"
        )
        self.producer: Optional[AIOKafkaProducer] = None

    async def start(self) -> None:
        """
        Start the Redpanda producer and establish connection.

        Creates an AIOKafkaProducer and starts it, establishing
        connection to the Redpanda cluster.

        Raises:
            ConnectionError: If connection to Redpanda fails.
        """
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.brokers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
            )
            await self.producer.start()
            logger.info(
                "Connected to Redpanda",
                extra={"brokers": self.brokers},
            )
        except KafkaError as e:
            logger.error(
                "Redpanda connection failed",
                extra={"brokers": self.brokers, "error": str(e)},
            )
            raise ConnectionError(
                f"Failed to connect to Redpanda at {self.brokers}: {e}"
            ) from e

    async def stop(self) -> None:
        """
        Stop the Redpanda producer and close connection.

        Flushes any pending messages and cleanly shuts down the producer.
        """
        if self.producer is not None:
            await self.producer.stop()
            self.producer = None
            logger.info(
                "Disconnected from Redpanda",
                extra={"brokers": self.brokers},
            )

    async def publish(
        self,
        topic: str,
        message: Dict[str, Any],
        partition_key: Optional[str] = None,
    ) -> None:
        """
        Publish a message to a Redpanda topic.

        Args:
            topic: The topic name to publish to.
            message: The message payload as a dictionary (serialized to JSON).
            partition_key: Optional key for partition routing. Messages with
                           the same key are guaranteed to go to the same partition.

        Raises:
            ConnectionError: If producer is not started.
            RuntimeError: If message send fails.
        """
        if self.producer is None:
            raise ConnectionError(
                "Redpanda producer is not started. Call start() first."
            )

        try:
            await self.producer.send_and_wait(
                topic=topic,
                value=message,
                key=partition_key,
            )

            log_extra: Dict[str, Any] = {"topic": topic}
            if partition_key is not None:
                log_extra["partition_key"] = partition_key

            logger.info("Event published", extra=log_extra)

        except KafkaError as e:
            logger.error(
                "Failed to publish event",
                extra={"topic": topic, "error": str(e)},
            )
            raise RuntimeError(f"Failed to publish to topic '{topic}': {e}") from e
