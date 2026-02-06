"""WebSocket connection manager for real-time notifications."""

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections for real-time notifications.

    Thread-safe connection management using asyncio.Lock.
    Supports broadcasting to all clients and sending to specific users.
    """

    def __init__(self) -> None:
        """Initialize the WebSocket manager."""
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """Add a new WebSocket connection.

        Args:
            websocket: The WebSocket connection to add.
            user_id: The user ID associated with this connection.
        """
        await websocket.accept()
        async with self._lock:
            # Disconnect existing connection if any
            if user_id in self._connections:
                await self._disconnect_internal(user_id)
            self._connections[user_id] = websocket
        logger.info(
            "User connected",
            extra={"user_id": user_id, "total_connections": len(self._connections)},
        )

    async def disconnect(self, user_id: str) -> None:
        """Remove a WebSocket connection.

        Args:
            user_id: The user ID to disconnect.
        """
        async with self._lock:
            await self._disconnect_internal(user_id)

    async def _disconnect_internal(self, user_id: str) -> None:
        """Internal disconnect without lock (must be called with lock held).

        Args:
            user_id: The user ID to disconnect.
        """
        if user_id in self._connections:
            del self._connections[user_id]
            logger.info(
                "User disconnected",
                extra={"user_id": user_id, "total_connections": len(self._connections)},
            )

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send message to all connected clients.

        Args:
            message: The message to broadcast.
        """
        async with self._lock:
            disconnected: list[str] = []
            for user_id, websocket in self._connections.items():
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.warning(
                        "Failed to send broadcast message",
                        extra={"user_id": user_id, "error": str(e)},
                    )
                    disconnected.append(user_id)

            for user_id in disconnected:
                await self._disconnect_internal(user_id)

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> bool:
        """Send message to a specific user.

        Args:
            user_id: The target user ID.
            message: The message to send.

        Returns:
            True if message was sent successfully, False otherwise.
        """
        async with self._lock:
            if user_id not in self._connections:
                logger.warning(
                    "User not connected",
                    extra={"user_id": user_id},
                )
                return False

            try:
                await self._connections[user_id].send_json(message)
                return True
            except Exception as e:
                logger.warning(
                    "Failed to send message to user",
                    extra={"user_id": user_id, "error": str(e)},
                )
                await self._disconnect_internal(user_id)
                return False

    @property
    def connection_count(self) -> int:
        """Get current connection count.

        Returns:
            Number of active WebSocket connections.
        """
        return len(self._connections)

    def get_connected_users(self) -> list[str]:
        """Get list of connected user IDs.

        Returns:
            List of connected user IDs.
        """
        return list(self._connections.keys())
