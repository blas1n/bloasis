"""
Unit tests for User Repository.

All external dependencies (PostgreSQL) are mocked.
Target: Increase overall coverage to 80%+.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import UserPreferencesRecord, UserRecord


class TestUserRepository:
    """Tests for UserRepository."""

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        mock = MagicMock()
        mock.get_session = MagicMock()
        return mock

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_user_by_id_no_postgres(self) -> None:
        """Should return None when postgres client is not available."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=None)
        result = await repository.get_user_by_id("test-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_id_success(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should return user when found."""
        from datetime import datetime

        from src.repositories import UserRepository

        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_record = MagicMock(spec=UserRecord)
        mock_record.user_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        mock_record.email = "test@example.com"
        mock_record.name = "Test User"
        mock_record.created_at = datetime(2025, 1, 26, 14, 30, 0)
        mock_record.updated_at = datetime(2025, 1, 26, 14, 30, 0)
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_session.execute.return_value = mock_result
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)
        result = await repository.get_user_by_id("123e4567-e89b-12d3-a456-426614174000")

        assert result is not None
        assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should return None when user not found."""
        from src.repositories import UserRepository

        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)
        result = await repository.get_user_by_id("nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_email_no_postgres(self) -> None:
        """Should return None when postgres client is not available."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=None)
        result = await repository.get_user_by_email("test@example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_by_email_success(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should return user record when found."""
        from src.repositories import UserRepository

        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_record = MagicMock(spec=UserRecord)
        mock_record.email = "test@example.com"
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_session.execute.return_value = mock_result
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)
        result = await repository.get_user_by_email("test@example.com")

        assert result is not None
        assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_create_user_no_postgres(self) -> None:
        """Should raise error when postgres client is not available."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=None)

        with pytest.raises(ValueError, match="Database client not available"):
            await repository.create_user("test@example.com", "password123", "Test User")

    @pytest.mark.asyncio
    async def test_create_user_success(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should create user with hashed password."""
        from datetime import datetime

        from src.repositories import UserRepository

        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing user
        mock_session.execute.return_value = mock_result

        # Create a real-looking user record after "commit"
        created_user = MagicMock(spec=UserRecord)
        created_user.user_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        created_user.email = "new@example.com"
        created_user.name = "New User"
        created_user.created_at = datetime.now()
        created_user.updated_at = datetime.now()

        # Make session.add capture the user and set it on refresh
        def capture_user(record):
            if isinstance(record, UserRecord):
                record.user_id = created_user.user_id
                record.email = created_user.email
                record.name = created_user.name
                record.created_at = created_user.created_at
                record.updated_at = created_user.updated_at

        mock_session.add = MagicMock(side_effect=capture_user)
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)

        # Mock get_user_by_email to return None (user doesn't exist)
        with patch.object(repository, "get_user_by_email", return_value=None):
            result = await repository.create_user("new@example.com", "securepass123", "New User")

        assert result is not None
        assert result.email == "new@example.com"
        assert result.name == "New User"

    @pytest.mark.asyncio
    async def test_validate_credentials_no_postgres(self) -> None:
        """Should return invalid when postgres client is not available."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=None)
        valid, user_id = await repository.validate_credentials("test@example.com", "password")

        assert valid is False
        assert user_id is None

    @pytest.mark.asyncio
    async def test_validate_credentials_user_not_found(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should return invalid when user not found."""
        from src.repositories import UserRepository

        mock_session = AsyncMock()
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)

        # Mock get_user_by_email to return None
        with patch.object(repository, "get_user_by_email", return_value=None):
            valid, user_id = await repository.validate_credentials("unknown@example.com", "password")

        assert valid is False
        assert user_id is None

    @pytest.mark.asyncio
    async def test_validate_credentials_correct_password(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should return valid when password matches."""
        import bcrypt

        from src.repositories import UserRepository

        # Create a hashed password
        password = "correctpassword"
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        mock_user = MagicMock(spec=UserRecord)
        mock_user.user_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        mock_user.password_hash = password_hash

        mock_session = AsyncMock()
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)

        # Mock get_user_by_email to return user with hashed password
        with patch.object(repository, "get_user_by_email", return_value=mock_user):
            valid, user_id = await repository.validate_credentials("test@example.com", password)

        assert valid is True
        assert user_id == "123e4567-e89b-12d3-a456-426614174000"

    @pytest.mark.asyncio
    async def test_validate_credentials_wrong_password(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should return invalid when password is wrong."""
        import bcrypt

        from src.repositories import UserRepository

        # Create a hashed password for a different password
        password_hash = bcrypt.hashpw("correctpassword".encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        mock_user = MagicMock(spec=UserRecord)
        mock_user.user_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        mock_user.password_hash = password_hash

        mock_session = AsyncMock()
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)

        # Mock get_user_by_email to return user
        with patch.object(repository, "get_user_by_email", return_value=mock_user):
            valid, user_id = await repository.validate_credentials("test@example.com", "wrongpassword")

        assert valid is False
        assert user_id is None


class TestPreferencesRepository:
    """Tests for preferences repository methods."""

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        mock = MagicMock()
        mock.get_session = MagicMock()
        return mock

    @pytest.mark.asyncio
    async def test_get_preferences_no_postgres(self) -> None:
        """Should return None when postgres client is not available."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=None)
        result = await repository.get_preferences("test-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_preferences_success(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should return preferences when found."""
        from src.repositories import UserRepository

        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_record = MagicMock(spec=UserPreferencesRecord)
        mock_record.user_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        mock_record.risk_profile = "aggressive"
        mock_record.max_portfolio_risk = Decimal("0.30")
        mock_record.max_position_size = Decimal("0.15")
        mock_record.preferred_sectors = ["Technology"]
        mock_record.enable_notifications = True
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_session.execute.return_value = mock_result
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)
        result = await repository.get_preferences("123e4567-e89b-12d3-a456-426614174000")

        assert result is not None
        assert result.risk_profile == "aggressive"
        assert result.max_portfolio_risk == Decimal("0.30")

    @pytest.mark.asyncio
    async def test_get_preferences_not_found(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should return None when preferences not found."""
        from src.repositories import UserRepository

        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)
        result = await repository.get_preferences("nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_preferences_no_postgres(self) -> None:
        """Should raise error when postgres client is not available."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=None)

        with pytest.raises(ValueError, match="Database client not available"):
            await repository.update_preferences("test-id", risk_profile="aggressive")

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_risk_profile(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should raise error for invalid risk profile."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=mock_postgres)

        with pytest.raises(ValueError, match="Invalid risk_profile"):
            await repository.update_preferences("test-id", risk_profile="invalid")

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_max_portfolio_risk(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should raise error when max_portfolio_risk is out of range."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=mock_postgres)

        with pytest.raises(ValueError, match="max_portfolio_risk must be between 0 and 1"):
            await repository.update_preferences("test-id", max_portfolio_risk=Decimal("1.5"))

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_max_position_size(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should raise error when max_position_size is out of range."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=mock_postgres)

        with pytest.raises(ValueError, match="max_position_size must be between 0 and 1"):
            await repository.update_preferences("test-id", max_position_size=Decimal("-0.1"))

    @pytest.mark.asyncio
    async def test_update_preferences_success(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should update preferences successfully."""
        from src.repositories import UserRepository

        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_record = MagicMock(spec=UserPreferencesRecord)
        mock_record.user_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        mock_record.risk_profile = "aggressive"
        mock_record.max_portfolio_risk = Decimal("0.30")
        mock_record.max_position_size = Decimal("0.15")
        mock_record.preferred_sectors = ["Technology"]
        mock_record.enable_notifications = True
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_session.execute.return_value = mock_result
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)
        result = await repository.update_preferences(
            "123e4567-e89b-12d3-a456-426614174000",
            risk_profile="aggressive",
            max_portfolio_risk=Decimal("0.30"),
            max_position_size=Decimal("0.15"),
            preferred_sectors=["Technology"],
            enable_notifications=True,
        )

        assert result is not None
        assert result.risk_profile == "aggressive"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_preferences_not_found(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should return None when preferences not found."""
        from src.repositories import UserRepository

        # Setup mock
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        repository = UserRepository(postgres_client=mock_postgres)
        result = await repository.update_preferences(
            "nonexistent-id",
            risk_profile="aggressive",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_create_preferences_no_postgres(self) -> None:
        """Should raise error when postgres client is not available."""
        from src.repositories import UserRepository

        repository = UserRepository(postgres_client=None)

        with pytest.raises(ValueError, match="Database client not available"):
            await repository.create_preferences("test-id")

    @pytest.mark.asyncio
    async def test_create_preferences_success(
        self,
        mock_postgres: MagicMock,
    ) -> None:
        """Should create default preferences."""
        from src.repositories import UserRepository

        # Setup mock
        mock_session = AsyncMock()
        mock_record = MagicMock(spec=UserPreferencesRecord)
        mock_record.user_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        mock_record.risk_profile = "moderate"
        mock_record.max_portfolio_risk = Decimal("0.20")
        mock_record.max_position_size = Decimal("0.10")
        mock_record.preferred_sectors = []
        mock_record.enable_notifications = True
        mock_postgres.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_postgres.get_session.return_value.__aexit__ = AsyncMock()

        # Capture added record
        captured_records = []

        def capture_add(record):
            captured_records.append(record)
            # Copy mock values to the record
            record.user_id = mock_record.user_id
            record.risk_profile = mock_record.risk_profile
            record.max_portfolio_risk = mock_record.max_portfolio_risk
            record.max_position_size = mock_record.max_position_size
            record.preferred_sectors = mock_record.preferred_sectors
            record.enable_notifications = mock_record.enable_notifications

        mock_session.add = MagicMock(side_effect=capture_add)

        repository = UserRepository(postgres_client=mock_postgres)
        result = await repository.create_preferences("123e4567-e89b-12d3-a456-426614174000")

        assert result is not None
        assert result.risk_profile == "moderate"
        mock_session.commit.assert_called_once()
