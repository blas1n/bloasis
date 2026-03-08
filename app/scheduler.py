"""Background scheduler — periodic analysis and order processing.

Runs as an asyncio coroutine within the FastAPI lifespan.
Handles:
- Analysis cycles for active users (10-minute interval)
- Order outbox processing (pending → broker submission)
- Order status polling (submitted → filled/cancelled)
- Reconciliation (broker vs DB diff detection, hourly)
"""

import asyncio
import logging
import uuid

from fastapi import FastAPI

from .config import settings
from .core.models import RiskProfile
from .repositories.order_repository import OrderRepository
from .repositories.portfolio_repository import PortfolioRepository
from .repositories.trade_repository import TradeRepository
from .repositories.user_repository import UserRepository
from .services.classification import ClassificationService
from .services.macro import MacroService
from .services.market_data import MarketDataService
from .services.market_regime import MarketRegimeService
from .services.order_processor import OrderProcessor
from .services.portfolio import PortfolioService
from .services.strategy import StrategyService

logger = logging.getLogger(__name__)


def _build_order_processor(app: FastAPI) -> OrderProcessor:
    """Build an OrderProcessor from app state."""
    redis = app.state.redis
    postgres = app.state.postgres

    user_repo = UserRepository(postgres=postgres)
    order_repo = OrderRepository(postgres=postgres)
    portfolio_repo = PortfolioRepository(postgres=postgres)
    trade_repo = TradeRepository(postgres=postgres)
    market_data_svc = MarketDataService(redis=redis, postgres=postgres)
    portfolio_svc = PortfolioService(
        redis=redis,
        portfolio_repo=portfolio_repo,
        trade_repo=trade_repo,
        market_data_svc=market_data_svc,
    )

    return OrderProcessor(
        order_repo=order_repo,
        user_repo=user_repo,
        portfolio_svc=portfolio_svc,
        redis=redis,
    )


async def _run_analysis_cycle(app: FastAPI) -> None:
    """Run one analysis cycle for all active users."""
    redis = app.state.redis
    postgres = app.state.postgres
    llm = app.state.llm

    user_repo = UserRepository(postgres=postgres)
    market_data_svc = MarketDataService(redis=redis, postgres=postgres)
    macro_svc = MacroService(redis=redis)
    regime_svc = MarketRegimeService(redis=redis, postgres=postgres, llm=llm, macro_svc=macro_svc)
    classification_svc = ClassificationService(redis=redis, llm=llm)
    strategy_svc = StrategyService(
        redis=redis,
        llm=llm,
        market_data=market_data_svc,
        market_regime=regime_svc,
        classification=classification_svc,
    )

    active_users = await _get_active_users(user_repo)

    if not active_users:
        logger.debug("No active trading users found")
        return

    logger.info("Scheduler: running analysis for %d active users", len(active_users))

    for user_id in active_users:
        try:
            prefs = await user_repo.get_preferences(user_id)
            risk_profile = RiskProfile(prefs.risk_profile) if prefs else RiskProfile.MODERATE
            excluded = list(prefs.excluded_sectors) if prefs and prefs.excluded_sectors else []

            await strategy_svc.run_analysis(
                user_id=user_id,
                risk_profile=risk_profile,
                excluded_sectors=excluded,
            )
            logger.info("Scheduler: analysis complete for user %s", user_id)
        except Exception:
            logger.error("Scheduler: analysis failed for user %s", user_id, exc_info=True)


async def _run_order_processing(app: FastAPI) -> None:
    """Process pending and unresolved orders."""
    processor: OrderProcessor = app.state.order_processor

    try:
        pending = await processor.process_pending_orders()
        if pending > 0:
            logger.info("Scheduler: processed %d pending orders", pending)
    except Exception:
        logger.error("Scheduler: pending order processing failed", exc_info=True)

    try:
        resolved = await processor.poll_unresolved_orders()
        if resolved > 0:
            logger.info("Scheduler: resolved %d unresolved orders", resolved)
    except Exception:
        logger.error("Scheduler: order polling failed", exc_info=True)


async def _run_reconciliation(app: FastAPI) -> None:
    """Reconcile broker vs DB positions for all active users."""
    processor: OrderProcessor = app.state.order_processor

    try:
        diffs = await processor.reconcile_with_broker()
        if diffs > 0:
            logger.warning("Scheduler: reconciliation found %d diffs", diffs)
        else:
            logger.info("Scheduler: reconciliation complete, no diffs")
    except Exception:
        logger.error("Scheduler: reconciliation failed", exc_info=True)


async def _get_active_users(user_repo: UserRepository, limit: int = 200) -> list[uuid.UUID]:
    """Get list of user IDs with trading enabled."""
    try:
        return await user_repo.get_active_trading_users(limit)
    except (OSError, RuntimeError):
        logger.error("Scheduler: failed to get active users", exc_info=True)
        return []


async def scheduler_loop(app: FastAPI) -> None:
    """Main scheduler loop — runs analysis + order processing at configured interval."""
    interval = settings.analysis_interval_seconds
    lock = asyncio.Lock()
    logger.info("Scheduler started (interval=%ds)", interval)

    try:
        while True:
            if lock.locked():
                logger.warning("Scheduler: previous cycle still running, skipping")
            else:
                async with lock:
                    try:
                        await _run_order_processing(app)
                        await _run_analysis_cycle(app)
                    except Exception:
                        logger.error("Scheduler cycle failed", exc_info=True)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Scheduler stopped")


async def reconciliation_loop(app: FastAPI) -> None:
    """Reconciliation loop — runs hourly."""
    reconciliation_interval = 3600
    logger.info("Reconciliation scheduler started (interval=%ds)", reconciliation_interval)

    try:
        while True:
            await asyncio.sleep(reconciliation_interval)
            try:
                await _run_reconciliation(app)
            except Exception:
                logger.error("Reconciliation cycle failed", exc_info=True)
    except asyncio.CancelledError:
        logger.info("Reconciliation scheduler stopped")


async def start_scheduler(app: FastAPI) -> None:
    """Start the background scheduler tasks."""
    app.state.order_processor = _build_order_processor(app)
    app.state.scheduler_task = asyncio.create_task(scheduler_loop(app))
    app.state.reconciliation_task = asyncio.create_task(reconciliation_loop(app))


async def stop_scheduler(app: FastAPI) -> None:
    """Stop all background scheduler tasks gracefully."""
    for task_name in ("scheduler_task", "reconciliation_task"):
        task = getattr(app.state, task_name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
