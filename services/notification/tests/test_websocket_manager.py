"""Tests for WebSocketManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.websocket_manager import WebSocketManager


class TestWebSocketManager:
    """Test cases for WebSocketManager class."""

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(
        self, ws_manager: WebSocketManager, mock_websocket: MagicMock
    ) -> None:
        """Test that connect accepts the WebSocket connection."""
        await ws_manager.connect(mock_websocket, "user-1")

        mock_websocket.accept.assert_called_once()
        assert ws_manager.connection_count == 1

    @pytest.mark.asyncio
    async def test_connect_multiple_users(
        self, ws_manager: WebSocketManager, mock_websocket_factory: callable
    ) -> None:
        """Test connecting multiple users."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()
        ws3 = mock_websocket_factory()

        await ws_manager.connect(ws1, "user-1")
        await ws_manager.connect(ws2, "user-2")
        await ws_manager.connect(ws3, "user-3")

        assert ws_manager.connection_count == 3
        assert set(ws_manager.get_connected_users()) == {"user-1", "user-2", "user-3"}

    @pytest.mark.asyncio
    async def test_connect_replaces_existing_connection(
        self, ws_manager: WebSocketManager, mock_websocket_factory: callable
    ) -> None:
        """Test that connecting with the same user_id replaces the old connection."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1, "user-1")
        assert ws_manager.connection_count == 1

        await ws_manager.connect(ws2, "user-1")
        assert ws_manager.connection_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(
        self, ws_manager: WebSocketManager, mock_websocket: MagicMock
    ) -> None:
        """Test that disconnect removes the connection."""
        await ws_manager.connect(mock_websocket, "user-1")
        assert ws_manager.connection_count == 1

        await ws_manager.disconnect("user-1")
        assert ws_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_user(
        self, ws_manager: WebSocketManager
    ) -> None:
        """Test disconnecting a non-existent user doesn't raise."""
        await ws_manager.disconnect("nonexistent-user")
        assert ws_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(
        self, ws_manager: WebSocketManager, mock_websocket_factory: callable
    ) -> None:
        """Test broadcast sends message to all connected clients."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()
        ws3 = mock_websocket_factory()

        await ws_manager.connect(ws1, "user-1")
        await ws_manager.connect(ws2, "user-2")
        await ws_manager.connect(ws3, "user-3")

        message = {"type": "test", "data": {"value": 123}}
        await ws_manager.broadcast(message)

        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)
        ws3.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(
        self, ws_manager: WebSocketManager, mock_websocket_factory: callable
    ) -> None:
        """Test broadcast removes connections that fail to send."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()
        ws2.send_json = AsyncMock(side_effect=Exception("Connection closed"))

        await ws_manager.connect(ws1, "user-1")
        await ws_manager.connect(ws2, "user-2")
        assert ws_manager.connection_count == 2

        message = {"type": "test", "data": {}}
        await ws_manager.broadcast(message)

        assert ws_manager.connection_count == 1
        assert ws_manager.get_connected_users() == ["user-1"]

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(
        self, ws_manager: WebSocketManager
    ) -> None:
        """Test broadcast with no connections doesn't raise."""
        message = {"type": "test", "data": {}}
        await ws_manager.broadcast(message)

    @pytest.mark.asyncio
    async def test_send_to_user_success(
        self, ws_manager: WebSocketManager, mock_websocket: MagicMock
    ) -> None:
        """Test send_to_user sends to specific user."""
        await ws_manager.connect(mock_websocket, "user-1")

        message = {"type": "personal", "data": {"secret": "value"}}
        result = await ws_manager.send_to_user("user-1", message)

        assert result is True
        mock_websocket.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_send_to_user_not_connected(
        self, ws_manager: WebSocketManager
    ) -> None:
        """Test send_to_user returns False for non-connected user."""
        message = {"type": "personal", "data": {}}
        result = await ws_manager.send_to_user("nonexistent-user", message)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_user_removes_failed_connection(
        self, ws_manager: WebSocketManager, mock_websocket: MagicMock
    ) -> None:
        """Test send_to_user removes connection on failure."""
        mock_websocket.send_json = AsyncMock(side_effect=Exception("Connection closed"))
        await ws_manager.connect(mock_websocket, "user-1")

        message = {"type": "personal", "data": {}}
        result = await ws_manager.send_to_user("user-1", message)

        assert result is False
        assert ws_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_connection_count_property(
        self, ws_manager: WebSocketManager, mock_websocket_factory: callable
    ) -> None:
        """Test connection_count property."""
        assert ws_manager.connection_count == 0

        await ws_manager.connect(mock_websocket_factory(), "user-1")
        assert ws_manager.connection_count == 1

        await ws_manager.connect(mock_websocket_factory(), "user-2")
        assert ws_manager.connection_count == 2

        await ws_manager.disconnect("user-1")
        assert ws_manager.connection_count == 1

    @pytest.mark.asyncio
    async def test_get_connected_users(
        self, ws_manager: WebSocketManager, mock_websocket_factory: callable
    ) -> None:
        """Test get_connected_users returns correct list."""
        await ws_manager.connect(mock_websocket_factory(), "alice")
        await ws_manager.connect(mock_websocket_factory(), "bob")
        await ws_manager.connect(mock_websocket_factory(), "charlie")

        users = ws_manager.get_connected_users()
        assert set(users) == {"alice", "bob", "charlie"}

    @pytest.mark.asyncio
    async def test_thread_safety_concurrent_operations(
        self, ws_manager: WebSocketManager, mock_websocket_factory: callable
    ) -> None:
        """Test thread safety with concurrent operations."""
        import asyncio

        async def connect_user(user_id: str) -> None:
            ws = mock_websocket_factory()
            await ws_manager.connect(ws, user_id)

        async def disconnect_user(user_id: str) -> None:
            await ws_manager.disconnect(user_id)

        # Connect 10 users concurrently
        await asyncio.gather(*[connect_user(f"user-{i}") for i in range(10)])
        assert ws_manager.connection_count == 10

        # Disconnect 5 users concurrently
        await asyncio.gather(*[disconnect_user(f"user-{i}") for i in range(5)])
        assert ws_manager.connection_count == 5
