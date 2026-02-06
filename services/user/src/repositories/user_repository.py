"""Repository for user and preferences data persistence."""

import uuid
from decimal import Decimal
from typing import Optional

import bcrypt
from shared.utils import PostgresClient
from sqlalchemy import select

from ..models import (
    User,
    UserPreferences,
    UserPreferencesRecord,
    UserRecord,
)


class UserRepository:
    """Repository for user_data.users and user_data.user_preferences tables."""

    def __init__(self, postgres_client: Optional[PostgresClient] = None) -> None:
        """
        Initialize the repository with a PostgreSQL client.

        Args:
            postgres_client: PostgreSQL client for database operations.
        """
        self.postgres = postgres_client

    # ==================== User Operations ====================

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get a user by their ID.

        Args:
            user_id: The user's UUID as string.

        Returns:
            User domain object if found, None otherwise.
        """
        if not self.postgres:
            return None

        async with self.postgres.get_session() as session:
            stmt = select(UserRecord).where(UserRecord.user_id == uuid.UUID(user_id))
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                return User.from_record(record)
            return None

    async def get_user_by_email(self, email: str) -> Optional[UserRecord]:
        """
        Get a user record by email.

        Args:
            email: The user's email address.

        Returns:
            UserRecord if found, None otherwise.
        """
        if not self.postgres:
            return None

        async with self.postgres.get_session() as session:
            stmt = select(UserRecord).where(UserRecord.email == email.lower())
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create_user(self, email: str, password: str, name: str) -> User:
        """
        Create a new user with hashed password.

        Args:
            email: User's email address.
            password: Plain text password (will be hashed).
            name: User's display name.

        Returns:
            Created User domain object.

        Raises:
            ValueError: If database client not available or email already exists.
        """
        if not self.postgres:
            raise ValueError("Database client not available")

        # Hash password with bcrypt
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        async with self.postgres.get_session() as session:
            # Check if email already exists
            existing = await self.get_user_by_email(email)
            if existing:
                raise ValueError(f"User with email {email} already exists")

            # Create user record
            user_record = UserRecord(
                email=email.lower(),
                password_hash=password_hash,
                name=name,
            )
            session.add(user_record)
            await session.commit()
            await session.refresh(user_record)

            # Create default preferences for the user
            preferences_record = UserPreferencesRecord(
                user_id=user_record.user_id,
                risk_profile="moderate",
                max_portfolio_risk=Decimal("0.20"),
                max_position_size=Decimal("0.10"),
                preferred_sectors=[],
                enable_notifications=True,
            )
            session.add(preferences_record)
            await session.commit()

            return User.from_record(user_record)

    async def validate_credentials(self, email: str, password: str) -> tuple[bool, Optional[str]]:
        """
        Validate user credentials.

        Args:
            email: User's email address.
            password: Plain text password to verify.

        Returns:
            Tuple of (valid, user_id). user_id is set only if valid=True.
        """
        if not self.postgres:
            return False, None

        user_record = await self.get_user_by_email(email)
        if not user_record:
            return False, None

        # Verify password with bcrypt
        if bcrypt.checkpw(password.encode("utf-8"), user_record.password_hash.encode("utf-8")):
            return True, str(user_record.user_id)

        return False, None

    # ==================== Preferences Operations ====================

    async def get_preferences(self, user_id: str) -> Optional[UserPreferences]:
        """
        Get user preferences by user ID.

        Args:
            user_id: The user's UUID as string.

        Returns:
            UserPreferences domain object if found, None otherwise.
        """
        if not self.postgres:
            return None

        async with self.postgres.get_session() as session:
            stmt = select(UserPreferencesRecord).where(
                UserPreferencesRecord.user_id == uuid.UUID(user_id)
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                return UserPreferences.from_record(record)
            return None

    async def update_preferences(
        self,
        user_id: str,
        risk_profile: Optional[str] = None,
        max_portfolio_risk: Optional[Decimal] = None,
        max_position_size: Optional[Decimal] = None,
        preferred_sectors: Optional[list[str]] = None,
        enable_notifications: Optional[bool] = None,
    ) -> Optional[UserPreferences]:
        """
        Update user preferences.

        Args:
            user_id: The user's UUID as string.
            risk_profile: New risk profile (optional).
            max_portfolio_risk: New max portfolio risk (optional).
            max_position_size: New max position size (optional).
            preferred_sectors: New preferred sectors (optional).
            enable_notifications: New notification setting (optional).

        Returns:
            Updated UserPreferences domain object if found, None otherwise.

        Raises:
            ValueError: If database client not available or invalid values.
        """
        if not self.postgres:
            raise ValueError("Database client not available")

        # Validate risk_profile if provided
        if risk_profile is not None:
            valid_profiles = ["conservative", "moderate", "aggressive"]
            if risk_profile not in valid_profiles:
                raise ValueError(f"Invalid risk_profile: {risk_profile}. Must be one of {valid_profiles}")

        # Validate max_portfolio_risk if provided
        if max_portfolio_risk is not None:
            if not (Decimal("0") <= max_portfolio_risk <= Decimal("1")):
                raise ValueError("max_portfolio_risk must be between 0 and 1")

        # Validate max_position_size if provided
        if max_position_size is not None:
            if not (Decimal("0") <= max_position_size <= Decimal("1")):
                raise ValueError("max_position_size must be between 0 and 1")

        async with self.postgres.get_session() as session:
            stmt = select(UserPreferencesRecord).where(
                UserPreferencesRecord.user_id == uuid.UUID(user_id)
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if not record:
                return None

            # Update fields if provided
            if risk_profile is not None:
                record.risk_profile = risk_profile
            if max_portfolio_risk is not None:
                record.max_portfolio_risk = max_portfolio_risk
            if max_position_size is not None:
                record.max_position_size = max_position_size
            if preferred_sectors is not None:
                record.preferred_sectors = preferred_sectors
            if enable_notifications is not None:
                record.enable_notifications = enable_notifications

            await session.commit()
            await session.refresh(record)

            return UserPreferences.from_record(record)

    async def create_preferences(self, user_id: str) -> UserPreferences:
        """
        Create default preferences for a user.

        Args:
            user_id: The user's UUID as string.

        Returns:
            Created UserPreferences domain object.

        Raises:
            ValueError: If database client not available.
        """
        if not self.postgres:
            raise ValueError("Database client not available")

        async with self.postgres.get_session() as session:
            record = UserPreferencesRecord(
                user_id=uuid.UUID(user_id),
                risk_profile="moderate",
                max_portfolio_risk=Decimal("0.20"),
                max_position_size=Decimal("0.10"),
                preferred_sectors=[],
                enable_notifications=True,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)

            return UserPreferences.from_record(record)
