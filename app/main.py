"""FastAPI application entry point.

Single process replacing 10 gRPC services.
Infrastructure: PostgreSQL + Redis only.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from .config import settings
from .log_config import setup_logging
from .rate_limit import limiter
from .shared.utils.response import CamelJSONResponse

setup_logging(log_level=settings.log_level)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — initialize and cleanup shared resources."""
    from shared.ai_clients.llm_client import LLMClient
    from shared.utils.postgres_client import PostgresClient
    from shared.utils.redis_client import RedisClient

    # Initialize infrastructure
    redis = RedisClient(
        host=settings.redis_host, port=settings.redis_port, password=settings.redis_password or None
    )
    postgres = PostgresClient(database_url=settings.database_url)
    llm = LLMClient(
        model=settings.llm_model,
        api_key=settings.llm_api_key or None,
        api_base=settings.llm_api_base,
    )

    # Initialize auth provider (JWKS + ES256)
    from bsvibe_auth import SupabaseAuthProvider

    auth_provider = SupabaseAuthProvider(
        jwt_secret=settings.supabase_jwt_secret,
        supabase_url=settings.supabase_url or None,
        service_role_key=settings.supabase_service_role_key or None,
        algorithms=["ES256"],
    )

    await redis.connect()
    await postgres.connect()
    logger.info("infrastructure_connected", services="Redis+PostgreSQL")

    broker_enabled = bool(settings.fernet_key)
    if not broker_enabled:
        logger.warning("broker_config_disabled", reason="CREDENTIAL_ENCRYPTION_KEY not set")

    # Store in app state for dependency injection
    app.state.redis = redis
    app.state.postgres = postgres
    app.state.llm = llm
    app.state.auth_provider = auth_provider
    app.state.broker_enabled = broker_enabled

    # Start background scheduler if enabled
    if settings.scheduler_enabled:
        from .scheduler import start_scheduler

        await start_scheduler(app)
        logger.info(
            "scheduler_started", interval_seconds=settings.analysis_interval_seconds
        )

    yield

    # Stop scheduler
    if settings.scheduler_enabled:
        from .scheduler import stop_scheduler

        await stop_scheduler(app)

    # Cleanup
    await redis.close()
    await postgres.close()
    logger.info("infrastructure_disconnected")


def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded. Please try again later."},
    )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="BLOASIS",
        description="AI-powered trading platform",
        version="2.0.0",
        lifespan=lifespan,
        default_response_class=CamelJSONResponse,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from .routers import (
        auth,
        backtesting,
        market,
        portfolios,
        signals,
        trading,
        users,
    )

    app.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
    app.include_router(users.router, prefix="/v1/users", tags=["users"])
    app.include_router(market.router, prefix="/v1/market", tags=["market"])
    app.include_router(portfolios.router, prefix="/v1/portfolios", tags=["portfolios"])
    app.include_router(trading.router, prefix="/v1/users", tags=["trading"])
    app.include_router(signals.router, prefix="/v1/users", tags=["signals"])
    app.include_router(backtesting.router, prefix="/v1/backtesting", tags=["backtesting"])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/metrics")
    async def metrics() -> str:
        """Stub metrics endpoint for Prometheus scraping. TODO: add real instrumentation."""
        return ""

    return app


app = create_app()
