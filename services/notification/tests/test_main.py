"""Tests for main.py FastAPI application."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Test cases for the /health endpoint."""

    def test_health_returns_healthy_status(self) -> None:
        """Test that health endpoint returns healthy status."""
        # We need to patch the dependencies before importing the app
        with (
            patch("src.main.ws_manager") as mock_ws_manager,
            patch("src.main.event_handlers") as mock_event_handlers,
        ):
            mock_ws_manager.connection_count = 5
            mock_event_handlers.is_running = True

            # Import after patching
            from src.main import app

            client = TestClient(app, raise_server_exceptions=False)

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["service"] == "notification"
            assert data["connections"] == 5
            assert data["consumer_running"] is True

    def test_health_with_zero_connections(self) -> None:
        """Test health endpoint with no connections."""
        with (
            patch("src.main.ws_manager") as mock_ws_manager,
            patch("src.main.event_handlers") as mock_event_handlers,
        ):
            mock_ws_manager.connection_count = 0
            mock_event_handlers.is_running = False

            from src.main import app

            client = TestClient(app, raise_server_exceptions=False)

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["connections"] == 0
            assert data["consumer_running"] is False


class TestLifespanManager:
    """Test cases for the lifespan manager."""

    @pytest.mark.asyncio
    async def test_lifespan_starts_and_stops_handlers(self) -> None:
        """Test that lifespan manager starts and stops event handlers."""
        with patch("src.main.event_handlers") as mock_event_handlers, patch("src.main.ws_manager"):
            mock_event_handlers.start = AsyncMock()
            mock_event_handlers.stop = AsyncMock()

            from src.main import app, lifespan

            async with lifespan(app):
                # Startup should have been called
                mock_event_handlers.start.assert_called_once()

            # Shutdown should have been called
            mock_event_handlers.stop.assert_called_once()


class TestAppConfiguration:
    """Test cases for app configuration."""

    def test_app_title_and_version(self) -> None:
        """Test app metadata is correctly set."""
        with patch("src.main.ws_manager"), patch("src.main.event_handlers"):
            from src.main import app

            assert app.title == "BLOASIS Notification Service"
            assert app.version == "0.1.0"
