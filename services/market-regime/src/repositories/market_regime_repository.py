"""Repository for market regime data persistence."""

from datetime import datetime
from typing import Optional

from shared.utils import PostgresClient
from sqlalchemy import select

from ..models import MarketRegimeRecord, RegimeData


class MarketRegimeRepository:
    """Repository for market_data.market_regimes table."""

    def __init__(self, postgres_client: Optional[PostgresClient] = None) -> None:
        self.postgres = postgres_client

    async def save(self, regime_data: RegimeData, timestamp: datetime) -> None:
        """Save a regime classification to the database."""
        if not self.postgres:
            return

        async with self.postgres.get_session() as session:
            record = MarketRegimeRecord(
                regime=regime_data.regime,
                confidence=regime_data.confidence,
                timestamp=timestamp,
                trigger=regime_data.trigger,
                analysis=None,
            )
            session.add(record)

    async def get_history(
        self, start_time: datetime, end_time: datetime
    ) -> list[MarketRegimeRecord]:
        """Get regime history within a time range."""
        if not self.postgres:
            return []

        async with self.postgres.get_session() as session:
            stmt = (
                select(MarketRegimeRecord)
                .where(
                    MarketRegimeRecord.timestamp >= start_time,
                    MarketRegimeRecord.timestamp <= end_time,
                )
                .order_by(MarketRegimeRecord.timestamp)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
