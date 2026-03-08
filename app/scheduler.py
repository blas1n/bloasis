"""Background scheduler — periodic analysis for active users.

Runs as an asyncio coroutine within the FastAPI lifespan.
Replaces the old microservices' periodic analysis (10-minute interval).
"""

import asyncio
import logging
import uuid

from fastapi import FastAPI

from .config import settings
from .core.models import RiskProfile
from .repositories.user_repository import UserRepository
from .services.classification import ClassificationService
from .services.macro import MacroService
from .services.market_data import MarketDataService
from .services.market_regime import MarketRegimeService
from .services.strategy import StrategyService

logger = logging.getLogger(__name__)


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

    # Get all users with trading enabled (via repository pattern)
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


async def _get_active_users(user_repo: UserRepository, limit: int = 200) -> list[uuid.UUID]:
    """Get list of user IDs with trading enabled (via repository pattern)."""
    try:
        return await user_repo.get_active_trading_users(limit)
    except Exception:
        logger.error("Scheduler: failed to get active users", exc_info=True)
        return []


async def scheduler_loop(app: FastAPI) -> None:
    """Main scheduler loop — runs analysis at configured interval."""
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
                        await _run_analysis_cycle(app)
                    except Exception:
                        logger.error("Scheduler cycle failed", exc_info=True)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("Scheduler stopped")


async def start_scheduler(app: FastAPI) -> None:
    """Start the background scheduler task."""
    app.state.scheduler_task = asyncio.create_task(scheduler_loop(app))


async def stop_scheduler(app: FastAPI) -> None:
    """Stop the background scheduler task gracefully."""
    task = getattr(app.state, "scheduler_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
