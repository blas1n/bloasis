"""
User Service - Domain Models and SQLAlchemy ORM.

Contains SQLAlchemy ORM models for database persistence,
and dataclasses for domain objects with Decimal precision for financial values.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# SQLAlchemy ORM Models


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class UserRecord(Base):
    """
    SQLAlchemy model for user_data.users table.

    Stores user account data with bcrypt hashed password.
    """

    __tablename__ = "users"
    __table_args__ = {"schema": "user_data"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class UserPreferencesRecord(Base):
    """
    SQLAlchemy model for user_data.user_preferences table.

    Stores user trading preferences with Decimal for financial risk values.
    """

    __tablename__ = "user_preferences"
    __table_args__ = {"schema": "user_data"}

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    risk_profile: Mapped[str] = mapped_column(String(50), nullable=False, default="moderate")
    max_portfolio_risk: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=4), nullable=False, default=Decimal("0.20")
    )
    max_position_size: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=4), nullable=False, default=Decimal("0.10")
    )
    preferred_sectors: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    enable_notifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# Domain Models


@dataclass
class User:
    """
    Data class representing a user account.

    Attributes:
        user_id: Unique user identifier (UUID as string).
        email: User's email address.
        name: Display name.
        created_at: ISO 8601 timestamp of account creation.
        updated_at: ISO 8601 timestamp of last update.
    """

    user_id: str
    email: str
    name: str
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: UserRecord) -> "User":
        """
        Create a User domain object from a database record.

        Args:
            record: SQLAlchemy UserRecord from database.

        Returns:
            User domain object.
        """
        return cls(
            user_id=str(record.user_id),
            email=record.email,
            name=record.name,
            created_at=record.created_at.isoformat() if record.created_at else "",
            updated_at=record.updated_at.isoformat() if record.updated_at else "",
        )


@dataclass
class UserPreferences:
    """
    Data class representing user trading preferences.

    All financial values use Decimal for precision.

    Attributes:
        user_id: User identifier (UUID as string).
        risk_profile: Risk tolerance level (conservative/moderate/aggressive).
        max_portfolio_risk: Maximum portfolio risk as Decimal (0-1).
        max_position_size: Maximum single position size as Decimal (0-1).
        preferred_sectors: List of preferred trading sectors.
        enable_notifications: Whether to receive notifications.
    """

    user_id: str
    risk_profile: str = "moderate"
    max_portfolio_risk: Decimal = Decimal("0.20")
    max_position_size: Decimal = Decimal("0.10")
    preferred_sectors: list[str] = field(default_factory=list)
    enable_notifications: bool = True

    @classmethod
    def from_record(cls, record: UserPreferencesRecord) -> "UserPreferences":
        """
        Create a UserPreferences domain object from a database record.

        Args:
            record: SQLAlchemy UserPreferencesRecord from database.

        Returns:
            UserPreferences domain object.
        """
        return cls(
            user_id=str(record.user_id),
            risk_profile=record.risk_profile,
            max_portfolio_risk=Decimal(str(record.max_portfolio_risk)),
            max_position_size=Decimal(str(record.max_position_size)),
            preferred_sectors=list(record.preferred_sectors) if record.preferred_sectors else [],
            enable_notifications=record.enable_notifications,
        )

    @classmethod
    def default_for_user(cls, user_id: str) -> "UserPreferences":
        """
        Create default preferences for a new user.

        Args:
            user_id: User identifier.

        Returns:
            UserPreferences with default values.
        """
        return cls(
            user_id=user_id,
            risk_profile="moderate",
            max_portfolio_risk=Decimal("0.20"),
            max_position_size=Decimal("0.10"),
            preferred_sectors=[],
            enable_notifications=True,
        )


def preferences_to_cache_dict(preferences: UserPreferences) -> dict:
    """
    Convert UserPreferences to a cache-friendly dict.

    Args:
        preferences: UserPreferences domain object.

    Returns:
        Dictionary suitable for JSON serialization.
    """
    return {
        "user_id": preferences.user_id,
        "risk_profile": preferences.risk_profile,
        "max_portfolio_risk": str(preferences.max_portfolio_risk),
        "max_position_size": str(preferences.max_position_size),
        "preferred_sectors": preferences.preferred_sectors,
        "enable_notifications": preferences.enable_notifications,
    }


def cache_dict_to_preferences(data: dict) -> UserPreferences:
    """
    Convert cached dict back to UserPreferences domain object.

    Args:
        data: Dictionary from cache.

    Returns:
        UserPreferences domain object.
    """
    return UserPreferences(
        user_id=data["user_id"],
        risk_profile=data["risk_profile"],
        max_portfolio_risk=Decimal(data["max_portfolio_risk"]),
        max_position_size=Decimal(data["max_position_size"]),
        preferred_sectors=data.get("preferred_sectors", []),
        enable_notifications=data.get("enable_notifications", True),
    )
