"""SQLAlchemy ORM models for BLOASIS.

Maps to existing PostgreSQL schemas:
- user_data: users, user_preferences, broker_config
- trading: portfolios, positions, trades
"""

import uuid as uuid_mod
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# --- user_data schema ---


class UserRecord(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "user_data"}

    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserPreferenceRecord(Base):
    __tablename__ = "user_preferences"
    __table_args__ = {"schema": "user_data"}

    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True)
    risk_profile: Mapped[str] = mapped_column(String, default="moderate")
    max_portfolio_risk: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0.20"))
    max_position_size: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0.10"))
    preferred_sectors: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=[])
    excluded_sectors: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=[])
    enable_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BrokerConfigRecord(Base):
    __tablename__ = "broker_config"
    __table_args__ = {"schema": "user_data"}

    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True)
    broker_type: Mapped[str] = mapped_column(String(50), primary_key=True, default="alpaca")
    config_key: Mapped[str] = mapped_column(String, primary_key=True)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# --- trading schema ---


class PortfolioRecord(Base):
    __tablename__ = "portfolios"
    __table_args__ = {"schema": "trading"}

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, unique=True, nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    invested_value: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    total_return: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    total_return_percent: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String, default="USD")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PositionRecord(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol"),
        {"schema": "trading"},
    )

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    current_value: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    unrealized_pnl_percent: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String, default="USD")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TradeRecord(Base):
    __tablename__ = "trades"
    __table_args__ = {"schema": "trading"}

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String, unique=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    total_value: Mapped[Decimal | None] = mapped_column(Numeric)
    commission: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric, default=Decimal("0"))
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ai_reason: Mapped[str | None] = mapped_column(String)


class OrderRecord(Base):
    """Order outbox table — records order intent before broker submission (Saga pattern)."""

    __tablename__ = "orders"
    __table_args__ = {"schema": "trading"}

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(100))
    broker_type: Mapped[str] = mapped_column(String(50), default="alpaca")
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), default="market")
    status: Mapped[str] = mapped_column(String(30), default="pending")  # OrderStatus enum values
    filled_qty: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("0"))
    filled_avg_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    error_message: Mapped[str | None] = mapped_column(Text)
    ai_reason: Mapped[str | None] = mapped_column(Text)
    risk_limits_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
