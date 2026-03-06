"""FastAPI dependency injection.

Provides service instances via FastAPI's Depends system.
All services are created per-request with shared infrastructure from app.state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request

from shared.ai_clients.llm_client import LLMClient
from shared.utils.postgres_client import PostgresClient
from shared.utils.redis_client import RedisClient

from .repositories.portfolio_repository import PortfolioRepository
from .repositories.trade_repository import TradeRepository
from .repositories.user_repository import UserRepository

if TYPE_CHECKING:
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
    return request.app.state.redis


def get_postgres(request: Request) -> PostgresClient:
    return request.app.state.postgres


def get_llm(request: Request) -> LLMClient:
    return request.app.state.llm


# --- Repository dependencies ---


def get_user_repo(postgres: PostgresClient = Depends(get_postgres)) -> UserRepository:
    return UserRepository(postgres=postgres)


def get_portfolio_repo(postgres: PostgresClient = Depends(get_postgres)) -> PortfolioRepository:
    return PortfolioRepository(postgres=postgres)


def get_trade_repo(postgres: PostgresClient = Depends(get_postgres)) -> TradeRepository:
    return TradeRepository(postgres=postgres)


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


def get_user_service(
    redis: RedisClient = Depends(get_redis),
    user_repo: UserRepository = Depends(get_user_repo),
) -> UserService:
    from .services.user import UserService

    return UserService(redis=redis, user_repo=user_repo)


def get_portfolio_service(
    redis: RedisClient = Depends(get_redis),
    portfolio_repo: PortfolioRepository = Depends(get_portfolio_repo),
    trade_repo: TradeRepository = Depends(get_trade_repo),
    market_data_svc: MarketDataService = Depends(get_market_data_service),
    user_repo: UserRepository = Depends(get_user_repo),
) -> PortfolioService:
    from .services.portfolio import PortfolioService

    return PortfolioService(
        redis=redis,
        portfolio_repo=portfolio_repo,
        trade_repo=trade_repo,
        market_data_svc=market_data_svc,
        user_repo=user_repo,
    )


def get_executor_service(
    redis: RedisClient = Depends(get_redis),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    market_data_svc: MarketDataService = Depends(get_market_data_service),
    user_repo: UserRepository = Depends(get_user_repo),
) -> ExecutorService:
    from .services.executor import ExecutorService

    return ExecutorService(
        redis=redis,
        portfolio_svc=portfolio_svc,
        market_data_svc=market_data_svc,
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


# --- Authentication dependency ---


async def get_current_user(
    request: Request,
    user_svc: UserService = Depends(get_user_service),
) -> str:
    """Extract and validate JWT from Authorization header. Returns user_id."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = auth_header.removeprefix("Bearer ")
    user_id = user_svc.validate_token(token)

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user_id


def verify_user_access(user_id: str, current_user: str = Depends(get_current_user)) -> str:
    """Verify the authenticated user matches the requested user_id."""
    if user_id != current_user:
        raise HTTPException(status_code=403, detail="Access denied")
    return user_id
