"""Repository for portfolio and position data persistence."""

from decimal import Decimal
from typing import Optional

from shared.utils import PostgresClient
from sqlalchemy import select

from ..models import Portfolio, PortfolioRecord, Position, PositionRecord


class PortfolioRepository:
    """Repository for trading.portfolios and trading.positions tables."""

    def __init__(self, postgres_client: Optional[PostgresClient] = None) -> None:
        """
        Initialize the repository with a PostgreSQL client.

        Args:
            postgres_client: PostgreSQL client for database operations.
        """
        self.postgres = postgres_client

    async def get_portfolio(self, user_id: str) -> Optional[PortfolioRecord]:
        """
        Get a user's portfolio record from the database.

        Args:
            user_id: The user's identifier.

        Returns:
            PortfolioRecord if found, None otherwise.
        """
        if not self.postgres:
            return None

        async with self.postgres.get_session() as session:
            stmt = select(PortfolioRecord).where(PortfolioRecord.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_positions(self, user_id: str) -> list[PositionRecord]:
        """
        Get all positions for a user from the database.

        Args:
            user_id: The user's identifier.

        Returns:
            List of PositionRecord objects for the user.
        """
        if not self.postgres:
            return []

        async with self.postgres.get_session() as session:
            stmt = (
                select(PositionRecord)
                .where(PositionRecord.user_id == user_id)
                .order_by(PositionRecord.symbol)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_full_portfolio(self, user_id: str, timestamp: str) -> Portfolio:
        """
        Get a user's complete portfolio with all calculated values.

        Args:
            user_id: The user's identifier.
            timestamp: ISO 8601 timestamp for the response.

        Returns:
            Portfolio domain object with all calculated totals.
        """
        portfolio_record = await self.get_portfolio(user_id)
        position_records = await self.get_positions(user_id)

        # Convert records to domain objects
        positions = [Position.from_record(r) for r in position_records]

        # Create portfolio with calculated totals
        portfolio = Portfolio.from_records(portfolio_record, positions, timestamp)
        portfolio.user_id = user_id

        return portfolio

    async def get_position_domain_objects(self, user_id: str) -> list[Position]:
        """
        Get all positions for a user as domain objects.

        Args:
            user_id: The user's identifier.

        Returns:
            List of Position domain objects with calculated values.
        """
        position_records = await self.get_positions(user_id)
        return [Position.from_record(r) for r in position_records]

    async def save_portfolio(self, portfolio_record: PortfolioRecord) -> None:
        """
        Save or update a portfolio record in the database.

        Args:
            portfolio_record: The portfolio record to save.
        """
        if not self.postgres:
            return

        async with self.postgres.get_session() as session:
            await session.merge(portfolio_record)

    async def save_position(self, position_record: PositionRecord) -> None:
        """
        Save or update a position record in the database.

        Args:
            position_record: The position record to save.
        """
        if not self.postgres:
            return

        async with self.postgres.get_session() as session:
            await session.merge(position_record)

    async def get_position_by_symbol(self, user_id: str, symbol: str) -> Optional[PositionRecord]:
        """
        Get a specific position by user_id and symbol.

        Args:
            user_id: The user's identifier.
            symbol: The stock ticker symbol.

        Returns:
            PositionRecord if found, None otherwise.
        """
        if not self.postgres:
            return None

        async with self.postgres.get_session() as session:
            stmt = select(PositionRecord).where(
                PositionRecord.user_id == user_id,
                PositionRecord.symbol == symbol,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_cash_balance(self, user_id: str, amount: Decimal, operation: str) -> Decimal:
        """
        Update cash balance for a user's portfolio.

        Args:
            user_id: User identifier.
            amount: Amount to set or add/subtract.
            operation: "set" for absolute value, "delta" for relative change.

        Returns:
            New cash balance after operation.

        Raises:
            ValueError: If operation is invalid or portfolio not found.
        """
        if not self.postgres:
            raise ValueError("Database client not available")

        async with self.postgres.get_session() as session:
            # Get current portfolio
            stmt = select(PortfolioRecord).where(PortfolioRecord.user_id == user_id)
            result = await session.execute(stmt)
            portfolio = result.scalar_one_or_none()

            if portfolio is None:
                # Create new portfolio for user
                portfolio = PortfolioRecord(
                    user_id=user_id,
                    cash_balance=Decimal("0"),
                    currency="USD",
                )
                session.add(portfolio)

            if operation == "set":
                portfolio.cash_balance = amount
            elif operation == "delta":
                portfolio.cash_balance = Decimal(str(portfolio.cash_balance)) + amount
            else:
                raise ValueError(f"Invalid operation: {operation}. Must be 'set' or 'delta'")

            await session.commit()
            return Decimal(str(portfolio.cash_balance))

    async def create_position(
        self,
        user_id: str,
        symbol: str,
        quantity: int,
        cost_per_share: Decimal,
        currency: str = "USD",
    ) -> PositionRecord:
        """
        Create a new position in the user's portfolio.

        Args:
            user_id: User identifier.
            symbol: Stock ticker symbol.
            quantity: Number of shares.
            cost_per_share: Cost per share for this purchase.
            currency: Currency code (default: "USD").

        Returns:
            Created PositionRecord.

        Raises:
            ValueError: If database client not available.
        """
        if not self.postgres:
            raise ValueError("Database client not available")

        async with self.postgres.get_session() as session:
            position = PositionRecord(
                user_id=user_id,
                symbol=symbol,
                quantity=quantity,
                avg_cost=cost_per_share,
                current_price=cost_per_share,  # Initial price is the cost
                currency=currency,
            )
            session.add(position)
            await session.commit()
            await session.refresh(position)
            return position

    async def update_position(
        self,
        user_id: str,
        symbol: str,
        quantity_delta: int,
        cost_per_share: Optional[Decimal] = None,
        current_price: Optional[Decimal] = None,
    ) -> Optional[PositionRecord]:
        """
        Update an existing position in the user's portfolio.

        When adding shares: recalculate avg_cost using weighted average.
        When reducing shares: keep avg_cost unchanged.

        Args:
            user_id: User identifier.
            symbol: Stock ticker symbol to update.
            quantity_delta: Quantity change (positive to add, negative to reduce).
            cost_per_share: Cost per share for added shares (required when adding).
            current_price: Current market price for the symbol.

        Returns:
            Updated PositionRecord if found, None otherwise.

        Raises:
            ValueError: If database client not available or invalid operation.
        """
        if not self.postgres:
            raise ValueError("Database client not available")

        async with self.postgres.get_session() as session:
            stmt = select(PositionRecord).where(
                PositionRecord.user_id == user_id,
                PositionRecord.symbol == symbol,
            )
            result = await session.execute(stmt)
            position = result.scalar_one_or_none()

            if position is None:
                return None

            old_quantity = position.quantity
            old_avg_cost = Decimal(str(position.avg_cost))
            new_quantity = old_quantity + quantity_delta

            if new_quantity < 0:
                raise ValueError(
                    f"Cannot reduce position below 0. Current: {old_quantity}, Delta: {quantity_delta}"
                )

            if quantity_delta > 0:
                # Adding shares - recalculate weighted average cost
                if cost_per_share is None:
                    raise ValueError("cost_per_share is required when adding shares")
                new_avg_cost = (
                    (old_quantity * old_avg_cost) + (quantity_delta * cost_per_share)
                ) / Decimal(new_quantity)
                position.avg_cost = new_avg_cost
            # When reducing shares, avg_cost remains unchanged

            position.quantity = new_quantity

            if current_price is not None:
                position.current_price = current_price

            await session.commit()
            await session.refresh(position)
            return position

    async def delete_position(self, user_id: str, symbol: str) -> bool:
        """
        Delete a position from the user's portfolio.

        Args:
            user_id: User identifier.
            symbol: Stock ticker symbol to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            ValueError: If database client not available.
        """
        if not self.postgres:
            raise ValueError("Database client not available")

        async with self.postgres.get_session() as session:
            # First check if position exists
            check_stmt = select(PositionRecord).where(
                PositionRecord.user_id == user_id,
                PositionRecord.symbol == symbol,
            )
            check_result = await session.execute(check_stmt)
            position = check_result.scalar_one_or_none()

            if position is None:
                return False

            # Delete the position
            await session.delete(position)
            await session.commit()
            return True
