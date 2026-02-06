"""Tests for EventHandlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.event_handlers import EventHandlers
from src.websocket_manager import WebSocketManager


class TestEventHandlers:
    """Test cases for EventHandlers class."""

    @pytest.fixture
    def event_handlers(self, ws_manager: WebSocketManager) -> EventHandlers:
        """Create EventHandlers instance with WebSocketManager."""
        return EventHandlers(ws_manager)

    @pytest.mark.asyncio
    async def test_handle_regime_change_broadcasts(
        self,
        event_handlers: EventHandlers,
        ws_manager: WebSocketManager,
        mock_websocket_factory: callable,
        sample_regime_change_event: dict,
    ) -> None:
        """Test regime change event is broadcast to all users."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1, "user-1")
        await ws_manager.connect(ws2, "user-2")

        await event_handlers._handle_regime_change(sample_regime_change_event)

        expected_message = {
            "type": "regime_change",
            "data": sample_regime_change_event,
        }
        ws1.send_json.assert_called_once_with(expected_message)
        ws2.send_json.assert_called_once_with(expected_message)

    @pytest.mark.asyncio
    async def test_handle_market_alert_broadcasts(
        self,
        event_handlers: EventHandlers,
        ws_manager: WebSocketManager,
        mock_websocket_factory: callable,
        sample_market_alert_event: dict,
    ) -> None:
        """Test market alert event is broadcast to all users."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1, "user-1")
        await ws_manager.connect(ws2, "user-2")

        await event_handlers._handle_market_alert(sample_market_alert_event)

        expected_message = {
            "type": "market_alert",
            "data": sample_market_alert_event,
        }
        ws1.send_json.assert_called_once_with(expected_message)
        ws2.send_json.assert_called_once_with(expected_message)

    @pytest.mark.asyncio
    async def test_handle_risk_alert_sends_to_user(
        self,
        event_handlers: EventHandlers,
        ws_manager: WebSocketManager,
        mock_websocket_factory: callable,
        sample_risk_alert_event: dict,
    ) -> None:
        """Test risk alert event is sent only to specific user."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1, "user-123")
        await ws_manager.connect(ws2, "user-456")

        await event_handlers._handle_risk_alert(sample_risk_alert_event)

        expected_message = {
            "type": "risk_alert",
            "data": sample_risk_alert_event,
        }
        ws1.send_json.assert_called_once_with(expected_message)
        ws2.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_risk_alert_missing_user_id(
        self,
        event_handlers: EventHandlers,
        ws_manager: WebSocketManager,
        mock_websocket_factory: callable,
    ) -> None:
        """Test risk alert without user_id logs warning."""
        ws1 = mock_websocket_factory()
        await ws_manager.connect(ws1, "user-1")

        event_without_user = {
            "event_type": "risk_alert",
            "alert_type": "position_limit",
            "severity": "medium",
        }

        await event_handlers._handle_risk_alert(event_without_user)

        ws1.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_execution_event_sends_to_user(
        self,
        event_handlers: EventHandlers,
        ws_manager: WebSocketManager,
        mock_websocket_factory: callable,
        sample_execution_event: dict,
    ) -> None:
        """Test execution event is sent only to specific user."""
        ws1 = mock_websocket_factory()
        ws2 = mock_websocket_factory()

        await ws_manager.connect(ws1, "user-123")
        await ws_manager.connect(ws2, "user-456")

        await event_handlers._handle_execution_event(sample_execution_event)

        expected_message = {
            "type": "order_executed",
            "data": sample_execution_event,
        }
        ws1.send_json.assert_called_once_with(expected_message)
        ws2.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_execution_event_missing_user_id(
        self,
        event_handlers: EventHandlers,
        ws_manager: WebSocketManager,
        mock_websocket_factory: callable,
        sample_execution_event_no_user: dict,
    ) -> None:
        """Test execution event without user_id logs warning."""
        ws1 = mock_websocket_factory()
        await ws_manager.connect(ws1, "user-1")

        await event_handlers._handle_execution_event(sample_execution_event_no_user)

        ws1.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_execution_event_user_not_connected(
        self,
        event_handlers: EventHandlers,
        ws_manager: WebSocketManager,
        sample_execution_event: dict,
    ) -> None:
        """Test execution event for non-connected user doesn't raise."""
        # No users connected
        await event_handlers._handle_execution_event(sample_execution_event)
        # Should not raise

    @pytest.mark.asyncio
    async def test_start_registers_handlers(
        self,
        event_handlers: EventHandlers,
        mock_event_consumer: MagicMock,
    ) -> None:
        """Test start registers all event handlers."""
        with patch(
            "src.event_handlers.EventConsumer", return_value=mock_event_consumer
        ):
            await event_handlers.start("localhost:9092", "test-group")

            # Verify handlers were registered
            assert mock_event_consumer.register_handler.call_count == 4

            # Verify consumer was started
            mock_event_consumer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_uses_correct_topics(
        self,
        event_handlers: EventHandlers,
    ) -> None:
        """Test start subscribes to correct topics."""
        assert EventHandlers.TOPICS == [
            "regime-events",
            "alert-events",
            "risk-events",
            "execution-events",
        ]

    @pytest.mark.asyncio
    async def test_stop_stops_consumer(
        self,
        event_handlers: EventHandlers,
        mock_event_consumer: MagicMock,
    ) -> None:
        """Test stop stops the consumer."""
        with patch(
            "src.event_handlers.EventConsumer", return_value=mock_event_consumer
        ):
            await event_handlers.start("localhost:9092")
            await event_handlers.stop()

            mock_event_consumer.stop.assert_called_once()
            assert event_handlers.consumer is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started(
        self,
        event_handlers: EventHandlers,
    ) -> None:
        """Test stop when consumer not started doesn't raise."""
        await event_handlers.stop()
        # Should not raise

    @pytest.mark.asyncio
    async def test_is_running_property(
        self,
        event_handlers: EventHandlers,
        mock_event_consumer: MagicMock,
    ) -> None:
        """Test is_running property reflects consumer state."""
        assert event_handlers.is_running is False

        with patch(
            "src.event_handlers.EventConsumer", return_value=mock_event_consumer
        ):
            await event_handlers.start("localhost:9092")
            assert event_handlers.is_running is True

            mock_event_consumer.is_running = False
            assert event_handlers.is_running is False

    @pytest.mark.asyncio
    async def test_broadcast_with_no_connections(
        self,
        event_handlers: EventHandlers,
        sample_regime_change_event: dict,
    ) -> None:
        """Test broadcast events with no connected users doesn't raise."""
        await event_handlers._handle_regime_change(sample_regime_change_event)
        await event_handlers._handle_market_alert({"alert_type": "test"})
        # Should not raise

    @pytest.mark.asyncio
    async def test_user_message_with_failed_send(
        self,
        event_handlers: EventHandlers,
        ws_manager: WebSocketManager,
        mock_websocket_factory: callable,
        sample_execution_event: dict,
    ) -> None:
        """Test user message removes connection on send failure."""
        ws = mock_websocket_factory()
        ws.send_json = AsyncMock(side_effect=Exception("Connection closed"))

        await ws_manager.connect(ws, "user-123")
        assert ws_manager.connection_count == 1

        await event_handlers._handle_execution_event(sample_execution_event)

        assert ws_manager.connection_count == 0
