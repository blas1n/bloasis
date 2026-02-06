"""BLOASIS Notification Service - FastAPI WebSocket Server.

This service consumes events from Redpanda and broadcasts them to
connected WebSocket clients. It handles both broadcast messages
(regime changes, market alerts) and targeted messages (risk alerts,
execution events).
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect

from .config import config
from .event_handlers import EventHandlers
from .websocket_manager import WebSocketManager

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global instances
ws_manager = WebSocketManager()
event_handlers = EventHandlers(ws_manager)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Starts and stops the event handlers on application startup/shutdown.

    Args:
        app: The FastAPI application.

    Yields:
        None
    """
    # Startup
    logger.info(
        "Starting Notification Service",
        extra={"service_name": config.service_name},
    )
    await event_handlers.start(config.redpanda_brokers)
    logger.info("Notification Service started")

    yield

    # Shutdown
    logger.info("Shutting down Notification Service")
    await event_handlers.stop()
    logger.info("Notification Service stopped")


app = FastAPI(
    title="BLOASIS Notification Service",
    description="Real-time notification service for BLOASIS trading platform",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str | int | bool]:
    """Health check endpoint.

    Returns:
        Health status including connection count and consumer status.
    """
    return {
        "status": "healthy",
        "service": config.service_name,
        "connections": ws_manager.connection_count,
        "consumer_running": event_handlers.is_running,
    }


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str = Query(..., description="User ID for message routing"),
) -> None:
    """WebSocket endpoint for real-time notifications.

    Clients connect with their user_id as a query parameter.
    The service will route targeted messages to specific users
    and broadcast general messages to all connected clients.

    Args:
        websocket: The WebSocket connection.
        user_id: The user ID for routing messages.
    """
    await ws_manager.connect(websocket, user_id)

    try:
        while True:
            # Keep connection alive and handle any client messages
            data = await websocket.receive_text()
            # Currently we don't process client messages, but log them
            logger.debug(
                "Received client message",
                extra={"user_id": user_id, "data": data},
            )
    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id)
    except Exception as e:
        logger.error(
            "WebSocket error",
            extra={"user_id": user_id, "error": str(e)},
        )
        await ws_manager.disconnect(user_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=config.ws_host,
        port=config.ws_port,
    )
