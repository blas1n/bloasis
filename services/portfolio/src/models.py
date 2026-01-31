"""
Portfolio Service - Domain Models and SQLAlchemy ORM.

Contains SQLAlchemy ORM models for database persistence,
and dataclasses for domain objects with Decimal precision for money.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# SQLAlchemy ORM Models


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class PortfolioRecord(Base):
    """
    SQLAlchemy model for trading.portfolios table.

    Stores user portfolio summary data with cash balance and metadata.
    """

    __tablename__ = "portfolios"
    __table_args__ = {"schema": "trading"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class PositionRecord(Base):
    """
    SQLAlchemy model for trading.positions table.

    Stores individual positions within a user's portfolio.
    Uses Decimal for all monetary values to ensure precision.
    """

    __tablename__ = "positions"
    __table_args__ = {"schema": "trading"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# Domain Models


@dataclass
class Position:
    """
    Data class representing a single position in the portfolio.

    All monetary values use Decimal for precision.

    Attributes:
        symbol: Stock ticker symbol (e.g., "AAPL", "GOOGL").
        quantity: Number of shares held.
        avg_cost: Average cost per share.
        current_price: Current market price per share.
        current_value: Total value of position (quantity * current_price).
        unrealized_pnl: Unrealized profit/loss in monetary amount.
        unrealized_pnl_percent: Unrealized profit/loss as percentage.
        currency: ISO 4217 currency code.
    """

    symbol: str
    quantity: int
    avg_cost: Decimal
    current_price: Decimal
    current_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: float
    currency: str = "USD"

    @classmethod
    def from_record(cls, record: PositionRecord) -> "Position":
        """
        Create a Position domain object from a database record.

        Args:
            record: SQLAlchemy PositionRecord from database.

        Returns:
            Position domain object with calculated values.
        """
        quantity = record.quantity
        avg_cost = Decimal(str(record.avg_cost))
        current_price = Decimal(str(record.current_price))

        current_value = current_price * Decimal(quantity)
        unrealized_pnl = (current_price - avg_cost) * Decimal(quantity)

        # Calculate percentage return
        if avg_cost > 0:
            unrealized_pnl_percent = float(((current_price - avg_cost) / avg_cost) * Decimal("100"))
        else:
            unrealized_pnl_percent = 0.0

        return cls(
            symbol=record.symbol,
            quantity=quantity,
            avg_cost=avg_cost,
            current_price=current_price,
            current_value=current_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_percent=unrealized_pnl_percent,
            currency=record.currency,
        )


@dataclass
class Portfolio:
    """
    Data class representing a user's complete portfolio.

    All monetary values use Decimal for precision.

    Attributes:
        user_id: User identifier.
        total_value: Total portfolio value (cash + invested).
        cash_balance: Available cash balance.
        invested_value: Total value invested in positions.
        total_return: Total return as percentage.
        total_return_amount: Total return in monetary amount.
        currency: ISO 4217 currency code.
        timestamp: ISO 8601 timestamp of when portfolio was last updated.
    """

    user_id: str
    total_value: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    total_return: float
    total_return_amount: Decimal
    currency: str = "USD"
    timestamp: Optional[str] = None

    @classmethod
    def from_records(
        cls,
        portfolio_record: Optional[PortfolioRecord],
        positions: list[Position],
        timestamp: str,
    ) -> "Portfolio":
        """
        Create a Portfolio domain object from database records.

        Args:
            portfolio_record: SQLAlchemy PortfolioRecord from database.
            positions: List of Position domain objects.
            timestamp: ISO 8601 timestamp string.

        Returns:
            Portfolio domain object with calculated totals.
        """
        if portfolio_record is None:
            # Return empty portfolio for new users
            return cls(
                user_id="",
                total_value=Decimal("0"),
                cash_balance=Decimal("0"),
                invested_value=Decimal("0"),
                total_return=0.0,
                total_return_amount=Decimal("0"),
                currency="USD",
                timestamp=timestamp,
            )

        cash_balance = Decimal(str(portfolio_record.cash_balance))
        currency = portfolio_record.currency

        # Calculate invested value from positions (use Decimal start value for type safety)
        invested_value: Decimal = sum((p.current_value for p in positions), Decimal("0"))
        total_value = cash_balance + invested_value

        # Calculate total cost basis
        total_cost_basis: Decimal = sum(
            (p.avg_cost * Decimal(p.quantity) for p in positions), Decimal("0")
        )

        # Calculate total return
        total_return_amount: Decimal = sum((p.unrealized_pnl for p in positions), Decimal("0"))

        # Calculate percentage return
        if total_cost_basis > 0:
            total_return = float((total_return_amount / total_cost_basis) * Decimal("100"))
        else:
            total_return = 0.0

        return cls(
            user_id=portfolio_record.user_id,
            total_value=total_value,
            cash_balance=cash_balance,
            invested_value=invested_value,
            total_return=total_return,
            total_return_amount=total_return_amount,
            currency=currency,
            timestamp=timestamp,
        )
