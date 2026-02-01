"""
Market Data Service - SQLAlchemy ORM Models.

Contains database models for OHLCV data and stock info persistence.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class OHLCVRecord(Base):
    """
    SQLAlchemy model for market_data.ohlcv_data table.

    Stores OHLCV (Open, High, Low, Close, Volume) price data.
    This is a TimescaleDB hypertable partitioned by timestamp.
    """

    __tablename__ = "ohlcv_data"
    __table_args__ = (
        Index("idx_ohlcv_symbol", "symbol", "timestamp"),
        Index("idx_ohlcv_symbol_interval", "symbol", "interval", "timestamp"),
        {"schema": "market_data"},
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    interval: Mapped[str] = mapped_column(String(10), default="1d")
    open: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    adj_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)


class StockInfoRecord(Base):
    """
    SQLAlchemy model for market_data.stock_info table.

    Stores stock metadata (company info, sector, market cap, etc.).
    """

    __tablename__ = "stock_info"
    __table_args__ = (
        Index("idx_stock_info_sector", "sector"),
        {"schema": "market_data"},
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    exchange: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2), nullable=True)
    pe_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    dividend_yield: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    fifty_two_week_high: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    fifty_two_week_low: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 8), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
