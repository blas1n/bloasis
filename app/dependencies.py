"""FastAPI dependency injection.

Provides service instances via FastAPI's Depends system.
All services are created per-request with shared infrastructure from app.state.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import jwt
from fastapi import Depends, HTTPException, Request

from shared.ai_clients.llm_client import LLMClient
from shared.utils.postgres_client import PostgresClient
from shared.utils.redis_client import RedisClient

from .repositories.order_repository import OrderRepository
from .repositories.portfolio_repository import PortfolioRepository
from .repositories.trade_repository import TradeRepository
from .repositories.user_repository import UserRepository

if TYPE_CHECKING:
    from .core.broker import BrokerAdapter
    from .services.backtesting import BacktestingService
    from .services.classification import ClassificationService
    from .services.executor import ExecutorService
    from .services.macro import MacroService
    from .services.market_data import MarketDataService
    from .services.market_regime import MarketRegimeService
    from .services.portfolio import PortfolioService
    from .services.strategy import StrategyService
    from .services.user import UserService

# --- Infrastructure dependencies ---


def get_redis(request: Request) -> RedisClient:
    result: RedisClient = request.app.state.redis
    return result


def get_postgres(request: Request) -> PostgresClient:
    result: PostgresClient = request.app.state.postgres
    return result


def get_llm(request: Request) -> LLMClient:
    result: LLMClient = request.app.state.llm
    return result


# --- Repository dependencies ---


def get_user_repo(postgres: PostgresClient = Depends(get_postgres)) -> UserRepository:
    return UserRepository(postgres=postgres)


def get_portfolio_repo(postgres: PostgresClient = Depends(get_postgres)) -> PortfolioRepository:
    return PortfolioRepository(postgres=postgres)


def get_trade_repo(postgres: PostgresClient = Depends(get_postgres)) -> TradeRepository:
    return TradeRepository(postgres=postgres)


def get_order_repo(postgres: PostgresClient = Depends(get_postgres)) -> OrderRepository:
    return OrderRepository(postgres=postgres)


# --- Authentication dependencies ---


def get_user_service(
    redis: RedisClient = Depends(get_redis),
    user_repo: UserRepository = Depends(get_user_repo),
) -> UserService:
    from .services.user import UserService

    return UserService(redis=redis, user_repo=user_repo)


async def get_current_user(request: Request) -> uuid.UUID:
    """Extract and validate Supabase JWT from Authorization header. Returns user_id as UUID."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = auth_header.removeprefix("Bearer ")
    try:
        jwks_client = request.app.state.jwks_client
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
        sub: str | None = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token: missing sub")
        return uuid.UUID(sub)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def verify_user_access(
    user_id: uuid.UUID, current_user: uuid.UUID = Depends(get_current_user)
) -> uuid.UUID:
    """Verify the authenticated user matches the requested user_id."""
    if user_id != current_user:
        raise HTTPException(status_code=403, detail="Access denied")
    return user_id


# --- Broker adapter dependency ---


async def get_broker_adapter(
    current_user: uuid.UUID = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repo),
) -> BrokerAdapter:
    from .services.brokers.factory import create_broker_adapter

    try:
        return await create_broker_adapter(current_user, user_repo)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="No broker credentials configured. Please set up your broker connection.",
        )


# --- Service dependencies ---


def get_market_data_service(
    redis: RedisClient = Depends(get_redis),
    postgres: PostgresClient = Depends(get_postgres),
) -> MarketDataService:
    from .services.market_data import MarketDataService

    return MarketDataService(redis=redis, postgres=postgres)


def get_macro_service(
    redis: RedisClient = Depends(get_redis),
) -> MacroService:
    from .services.macro import MacroService

    return MacroService(redis=redis)


def get_market_regime_service(
    redis: RedisClient = Depends(get_redis),
    postgres: PostgresClient = Depends(get_postgres),
    llm: LLMClient = Depends(get_llm),
    macro_svc: MacroService = Depends(get_macro_service),
) -> MarketRegimeService:
    from .services.market_regime import MarketRegimeService

    return MarketRegimeService(redis=redis, postgres=postgres, llm=llm, macro_svc=macro_svc)


def get_classification_service(
    redis: RedisClient = Depends(get_redis),
    llm: LLMClient = Depends(get_llm),
) -> ClassificationService:
    from .services.classification import ClassificationService

    return ClassificationService(redis=redis, llm=llm)


def get_portfolio_service(
    redis: RedisClient = Depends(get_redis),
    portfolio_repo: PortfolioRepository = Depends(get_portfolio_repo),
    trade_repo: TradeRepository = Depends(get_trade_repo),
    market_data_svc: MarketDataService = Depends(get_market_data_service),
) -> PortfolioService:
    from .services.portfolio import PortfolioService

    return PortfolioService(
        redis=redis,
        portfolio_repo=portfolio_repo,
        trade_repo=trade_repo,
        market_data_svc=market_data_svc,
    )


def get_executor_service(
    redis: RedisClient = Depends(get_redis),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    market_data_svc: MarketDataService = Depends(get_market_data_service),
    broker: BrokerAdapter = Depends(get_broker_adapter),
    order_repo: OrderRepository = Depends(get_order_repo),
    user_repo: UserRepository = Depends(get_user_repo),
) -> ExecutorService:
    from .services.executor import ExecutorService

    return ExecutorService(
        redis=redis,
        portfolio_svc=portfolio_svc,
        market_data_svc=market_data_svc,
        broker=broker,
        order_repo=order_repo,
        user_repo=user_repo,
    )


def get_backtesting_service(
    redis: RedisClient = Depends(get_redis),
    market_data_svc: MarketDataService = Depends(get_market_data_service),
) -> BacktestingService:
    from .services.backtesting import BacktestingService

    return BacktestingService(redis=redis, market_data_svc=market_data_svc)


def get_strategy_service(
    redis: RedisClient = Depends(get_redis),
    llm: LLMClient = Depends(get_llm),
    market_data: MarketDataService = Depends(get_market_data_service),
    market_regime: MarketRegimeService = Depends(get_market_regime_service),
    classification: ClassificationService = Depends(get_classification_service),
) -> StrategyService:
    from .services.strategy import StrategyService

    return StrategyService(
        redis=redis,
        llm=llm,
        market_data=market_data,
        market_regime=market_regime,
        classification=classification,
    )
