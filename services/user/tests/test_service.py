"""
Unit tests for User Service.

All external dependencies (Redis, PostgreSQL) are mocked.
Target: 80%+ code coverage.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models import User, UserPreferences


class TestUser:
    """Tests for User domain model."""

    def test_user_creation(self) -> None:
        """Should create User with all fields."""
        user = User(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            email="test@example.com",
            name="Test User",
            created_at="2025-01-26T14:30:00Z",
            updated_at="2025-01-26T14:30:00Z",
        )
        assert user.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert user.email == "test@example.com"
        assert user.name == "Test User"

    def test_user_from_record(self) -> None:
        """Should create User from database record."""
        import uuid
        from datetime import datetime

        from src.models import UserRecord

        mock_record = MagicMock(spec=UserRecord)
        mock_record.user_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        mock_record.email = "test@example.com"
        mock_record.name = "Test User"
        mock_record.created_at = datetime(2025, 1, 26, 14, 30, 0)
        mock_record.updated_at = datetime(2025, 1, 26, 14, 30, 0)

        user = User.from_record(mock_record)

        assert user.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert user.email == "test@example.com"
        assert user.name == "Test User"


class TestUserPreferences:
    """Tests for UserPreferences domain model."""

    def test_preferences_creation(self) -> None:
        """Should create UserPreferences with all fields."""
        prefs = UserPreferences(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            risk_profile="aggressive",
            max_portfolio_risk=Decimal("0.30"),
            max_position_size=Decimal("0.15"),
            preferred_sectors=["Technology", "Healthcare"],
            enable_notifications=True,
        )
        assert prefs.risk_profile == "aggressive"
        assert prefs.max_portfolio_risk == Decimal("0.30")
        assert prefs.preferred_sectors == ["Technology", "Healthcare"]

    def test_preferences_default_values(self) -> None:
        """Should have correct default values."""
        prefs = UserPreferences(user_id="test-id")
        assert prefs.risk_profile == "moderate"
        assert prefs.max_portfolio_risk == Decimal("0.20")
        assert prefs.max_position_size == Decimal("0.10")
        assert prefs.preferred_sectors == []
        assert prefs.enable_notifications is True

    def test_preferences_from_record(self) -> None:
        """Should create UserPreferences from database record."""
        import uuid

        from src.models import UserPreferencesRecord

        mock_record = MagicMock(spec=UserPreferencesRecord)
        mock_record.user_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
        mock_record.risk_profile = "conservative"
        mock_record.max_portfolio_risk = Decimal("0.10")
        mock_record.max_position_size = Decimal("0.05")
        mock_record.preferred_sectors = ["Utilities", "Consumer Staples"]
        mock_record.enable_notifications = False

        prefs = UserPreferences.from_record(mock_record)

        assert prefs.risk_profile == "conservative"
        assert prefs.max_portfolio_risk == Decimal("0.10")
        assert prefs.preferred_sectors == ["Utilities", "Consumer Staples"]
        assert prefs.enable_notifications is False

    def test_default_for_user(self) -> None:
        """Should create default preferences for a user."""
        prefs = UserPreferences.default_for_user("test-user-id")

        assert prefs.user_id == "test-user-id"
        assert prefs.risk_profile == "moderate"
        assert prefs.max_portfolio_risk == Decimal("0.20")


class TestPreferencesCaching:
    """Tests for preferences cache helper functions."""

    def test_preferences_cache_roundtrip(self) -> None:
        """Should convert preferences to cache dict and back."""
        from src.models import cache_dict_to_preferences, preferences_to_cache_dict

        prefs = UserPreferences(
            user_id="test-id",
            risk_profile="aggressive",
            max_portfolio_risk=Decimal("0.25"),
            max_position_size=Decimal("0.12"),
            preferred_sectors=["Technology"],
            enable_notifications=True,
        )

        cache_dict = preferences_to_cache_dict(prefs)
        restored = cache_dict_to_preferences(cache_dict)

        assert restored.user_id == prefs.user_id
        assert restored.risk_profile == prefs.risk_profile
        assert restored.max_portfolio_risk == prefs.max_portfolio_risk
        assert restored.max_position_size == prefs.max_position_size
        assert restored.preferred_sectors == prefs.preferred_sectors
        assert restored.enable_notifications == prefs.enable_notifications


class TestUserServicer:
    """Tests for UserServicer gRPC implementation."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.client = MagicMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        mock = MagicMock()
        mock.engine = MagicMock()
        return mock

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock Repository for database operations."""
        mock = AsyncMock()
        mock.get_user_by_id = AsyncMock(return_value=None)
        mock.get_user_by_email = AsyncMock(return_value=None)
        mock.create_user = AsyncMock()
        mock.validate_credentials = AsyncMock(return_value=(False, None))
        mock.get_preferences = AsyncMock(return_value=None)
        mock.update_preferences = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_get_user_success(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return user data."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.get_user_by_id.return_value = User(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            email="test@example.com",
            name="Test User",
            created_at="2025-01-26T14:30:00Z",
            updated_at="2025-01-26T14:30:00Z",
        )

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.GetUserRequest(user_id="123e4567-e89b-12d3-a456-426614174000")
        response = await servicer.GetUser(request, mock_context)

        assert response.user.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert response.user.email == "test@example.com"
        assert response.user.name == "Test User"
        mock_repository.get_user_by_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_not_found(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return NOT_FOUND when user doesn't exist."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.get_user_by_id.return_value = None

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.GetUserRequest(user_id="nonexistent-id")
        await servicer.GetUser(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_user_missing_user_id(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when user_id is missing."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.GetUserRequest(user_id="")
        await servicer.GetUser(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_create_user_success(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should create user successfully."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.create_user.return_value = User(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            email="new@example.com",
            name="New User",
            created_at="2025-01-26T14:30:00Z",
            updated_at="2025-01-26T14:30:00Z",
        )

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.CreateUserRequest(
            email="new@example.com",
            password="securepass123",
            name="New User",
        )
        response = await servicer.CreateUser(request, mock_context)

        assert response.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert response.user.email == "new@example.com"
        mock_repository.create_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_user_missing_email(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when email is missing."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.CreateUserRequest(
            email="",
            password="securepass123",
            name="New User",
        )
        await servicer.CreateUser(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_create_user_missing_password(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when password is missing."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.CreateUserRequest(
            email="test@example.com",
            password="",
            name="New User",
        )
        await servicer.CreateUser(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_create_user_missing_name(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when name is missing."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.CreateUserRequest(
            email="test@example.com",
            password="securepass123",
            name="",
        )
        await servicer.CreateUser(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_create_user_invalid_email(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error for invalid email format."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.CreateUserRequest(
            email="invalid-email",
            password="securepass123",
            name="New User",
        )
        await servicer.CreateUser(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_create_user_short_password(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error for short password."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.CreateUserRequest(
            email="test@example.com",
            password="short",
            name="New User",
        )
        await servicer.CreateUser(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_create_user_already_exists(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return ALREADY_EXISTS when email is taken."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.create_user.side_effect = ValueError("User already exists")

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.CreateUserRequest(
            email="existing@example.com",
            password="securepass123",
            name="New User",
        )
        await servicer.CreateUser(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_validate_credentials_success(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should validate correct credentials."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.validate_credentials.return_value = (
            True,
            "123e4567-e89b-12d3-a456-426614174000",
        )

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.ValidateCredentialsRequest(
            email="test@example.com",
            password="correctpassword",
        )
        response = await servicer.ValidateCredentials(request, mock_context)

        assert response.valid is True
        assert response.user_id == "123e4567-e89b-12d3-a456-426614174000"

    @pytest.mark.asyncio
    async def test_validate_credentials_invalid(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should reject invalid credentials."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.validate_credentials.return_value = (False, None)

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.ValidateCredentialsRequest(
            email="test@example.com",
            password="wrongpassword",
        )
        response = await servicer.ValidateCredentials(request, mock_context)

        assert response.valid is False
        assert response.user_id == ""

    @pytest.mark.asyncio
    async def test_validate_credentials_missing_fields(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return invalid for missing fields."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.ValidateCredentialsRequest(email="", password="")
        response = await servicer.ValidateCredentials(request, mock_context)

        assert response.valid is False


class TestGetUserPreferences:
    """Tests for GetUserPreferences gRPC method."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        return MagicMock()

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock Repository."""
        mock = AsyncMock()
        mock.get_preferences = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_get_preferences_cache_hit(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return cached preferences on cache hit."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        # Setup cache hit
        mock_redis.get.return_value = {
            "user_id": "test-user-id",
            "risk_profile": "aggressive",
            "max_portfolio_risk": "0.30",
            "max_position_size": "0.15",
            "preferred_sectors": ["Technology"],
            "enable_notifications": True,
        }

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.GetPreferencesRequest(user_id="test-user-id")
        response = await servicer.GetUserPreferences(request, mock_context)

        assert response.preferences.risk_profile == "aggressive"
        assert response.preferences.max_portfolio_risk == "0.30"
        mock_redis.get.assert_called_once()
        mock_repository.get_preferences.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_preferences_cache_miss(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should query database and cache on cache miss."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        # Setup cache miss
        mock_redis.get.return_value = None

        # Setup repository response
        mock_repository.get_preferences.return_value = UserPreferences(
            user_id="test-user-id",
            risk_profile="moderate",
            max_portfolio_risk=Decimal("0.20"),
            max_position_size=Decimal("0.10"),
            preferred_sectors=["Healthcare"],
            enable_notifications=True,
        )

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.GetPreferencesRequest(user_id="test-user-id")
        response = await servicer.GetUserPreferences(request, mock_context)

        assert response.preferences.risk_profile == "moderate"
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_preferences_not_found(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return NOT_FOUND when preferences don't exist."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.get_preferences.return_value = None

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.GetPreferencesRequest(user_id="nonexistent-id")
        await servicer.GetUserPreferences(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_preferences_missing_user_id(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when user_id is missing."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.GetPreferencesRequest(user_id="")
        await servicer.GetUserPreferences(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_preferences_no_redis(
        self,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should work without Redis client."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.get_preferences.return_value = UserPreferences(
            user_id="test-user-id",
            risk_profile="conservative",
            max_portfolio_risk=Decimal("0.10"),
            max_position_size=Decimal("0.05"),
            preferred_sectors=[],
            enable_notifications=False,
        )

        servicer = UserServicer(
            redis_client=None,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.GetPreferencesRequest(user_id="test-user-id")
        response = await servicer.GetUserPreferences(request, mock_context)

        assert response.preferences.risk_profile == "conservative"


class TestUpdateUserPreferences:
    """Tests for UpdateUserPreferences gRPC method."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        return MagicMock()

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock Repository."""
        mock = AsyncMock()
        mock.update_preferences = AsyncMock()
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_update_preferences_success(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should update preferences successfully."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.update_preferences.return_value = UserPreferences(
            user_id="test-user-id",
            risk_profile="aggressive",
            max_portfolio_risk=Decimal("0.30"),
            max_position_size=Decimal("0.15"),
            preferred_sectors=["Technology"],
            enable_notifications=True,
        )

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.UpdatePreferencesRequest(
            user_id="test-user-id",
            preferences=user_pb2.UserPreferences(
                risk_profile="aggressive",
                max_portfolio_risk="0.30",
                max_position_size="0.15",
                preferred_sectors=["Technology"],
            ),
        )
        response = await servicer.UpdateUserPreferences(request, mock_context)

        assert response.preferences.risk_profile == "aggressive"
        mock_repository.update_preferences.assert_called_once()
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_preferences_not_found(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return NOT_FOUND when preferences don't exist."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.update_preferences.return_value = None

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.UpdatePreferencesRequest(
            user_id="nonexistent-id",
            preferences=user_pb2.UserPreferences(risk_profile="aggressive"),
        )
        await servicer.UpdateUserPreferences(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_update_preferences_missing_user_id(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when user_id is missing."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.UpdatePreferencesRequest(user_id="")
        await servicer.UpdateUserPreferences(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_update_preferences_missing_preferences(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error when preferences is missing."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.UpdatePreferencesRequest(user_id="test-user-id")
        await servicer.UpdateUserPreferences(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_update_preferences_invalid_risk_profile(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return error for invalid risk_profile."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.update_preferences.side_effect = ValueError("Invalid risk_profile")

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.UpdatePreferencesRequest(
            user_id="test-user-id",
            preferences=user_pb2.UserPreferences(risk_profile="invalid"),
        )
        await servicer.UpdateUserPreferences(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_update_preferences_invalidates_cache(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should invalidate cache after updating preferences."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_repository.update_preferences.return_value = UserPreferences(
            user_id="test-user-id",
            risk_profile="moderate",
            max_portfolio_risk=Decimal("0.20"),
            max_position_size=Decimal("0.10"),
            preferred_sectors=[],
            enable_notifications=True,
        )

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
        )

        request = user_pb2.UpdatePreferencesRequest(
            user_id="test-user-id",
            preferences=user_pb2.UserPreferences(risk_profile="moderate"),
        )
        await servicer.UpdateUserPreferences(request, mock_context)

        mock_redis.delete.assert_called_once_with("user:test-user-id:preferences")


class TestServiceHelperFunctions:
    """Tests for service helper functions."""

    def test_user_to_proto(self) -> None:
        """Should convert User domain object to proto."""
        from src.service import _user_to_proto

        user = User(
            user_id="test-id",
            email="test@example.com",
            name="Test User",
            created_at="2025-01-26T14:30:00Z",
            updated_at="2025-01-26T14:30:00Z",
        )

        proto = _user_to_proto(user)

        assert proto.user_id == "test-id"
        assert proto.email == "test@example.com"
        assert proto.name == "Test User"

    def test_preferences_to_proto(self) -> None:
        """Should convert UserPreferences domain object to proto."""
        from src.service import _preferences_to_proto

        prefs = UserPreferences(
            user_id="test-id",
            risk_profile="aggressive",
            max_portfolio_risk=Decimal("0.30"),
            max_position_size=Decimal("0.15"),
            preferred_sectors=["Technology", "Healthcare"],
            enable_notifications=True,
        )

        proto = _preferences_to_proto(prefs)

        assert proto.user_id == "test-id"
        assert proto.risk_profile == "aggressive"
        assert proto.max_portfolio_risk == "0.30"
        assert proto.max_position_size == "0.15"
        assert list(proto.preferred_sectors) == ["Technology", "Healthcare"]
        assert proto.enable_notifications is True

    def test_preferences_cache_key(self) -> None:
        """Should generate correct cache key."""
        from src.service import _preferences_cache_key

        key = _preferences_cache_key("user-123")
        assert key == "user:user-123:preferences"


class TestServicerErrors:
    """Test error handling in servicer."""

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_get_user_exception(self, mock_context: MagicMock) -> None:
        """Should handle exceptions gracefully."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        # Create mock that raises exception
        mock_repository = AsyncMock()
        mock_repository.get_user_by_id = AsyncMock(side_effect=Exception("DB error"))

        servicer = UserServicer(
            redis_client=None,
            postgres_client=None,
            repository=mock_repository,
        )

        request = user_pb2.GetUserRequest(user_id="test-id")
        await servicer.GetUser(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_get_preferences_exception(self, mock_context: MagicMock) -> None:
        """Should handle exceptions gracefully."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        # Create mock that raises exception
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=None,
        )

        request = user_pb2.GetPreferencesRequest(user_id="test-id")
        await servicer.GetUserPreferences(request, mock_context)

        mock_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_validate_credentials_exception(self, mock_context: MagicMock) -> None:
        """Should handle exceptions gracefully."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        # Create mock that raises exception
        mock_repository = AsyncMock()
        mock_repository.validate_credentials = AsyncMock(side_effect=Exception("DB error"))

        servicer = UserServicer(
            redis_client=None,
            postgres_client=None,
            repository=mock_repository,
        )

        request = user_pb2.ValidateCredentialsRequest(
            email="test@example.com",
            password="password",
        )
        response = await servicer.ValidateCredentials(request, mock_context)

        assert response.valid is False


class TestMainModule:
    """Tests for main.py module."""

    @pytest.mark.asyncio
    async def test_serve_initializes_clients(self) -> None:
        """Should initialize all clients on serve."""
        import asyncio
        from unittest.mock import patch

        # Import the module first so patches work correctly
        import src.main as main_module

        with (
            patch.object(main_module, "RedisClient") as mock_redis_cls,
            patch.object(main_module, "PostgresClient") as mock_postgres_cls,
            patch.object(main_module, "grpc") as mock_grpc,
            patch.object(main_module, "health") as mock_health_module,
            patch.object(main_module, "health_pb2") as mock_health_pb2,
            patch.object(main_module, "health_pb2_grpc"),
            patch.object(main_module, "user_pb2_grpc"),
            patch.object(main_module, "config") as mock_config,
        ):
            # Setup mocks
            mock_config.service_name = "user-test"
            mock_config.grpc_port = 50058
            mock_config.consul_enabled = False

            mock_redis = AsyncMock()
            mock_redis_cls.return_value = mock_redis

            mock_postgres = AsyncMock()
            mock_postgres_cls.return_value = mock_postgres

            mock_server = MagicMock()
            mock_server.add_insecure_port = MagicMock()
            mock_server.start = AsyncMock()
            mock_server.wait_for_termination = AsyncMock(side_effect=asyncio.CancelledError())
            mock_server.stop = AsyncMock()
            mock_grpc.aio.server.return_value = mock_server

            mock_health_servicer = MagicMock()
            mock_health_module.HealthServicer.return_value = mock_health_servicer

            mock_health_pb2.HealthCheckResponse.SERVING = 1

            # Run serve (will be cancelled immediately)
            try:
                await main_module.serve()
            except asyncio.CancelledError:
                pass

            # Verify clients were initialized
            mock_redis.connect.assert_called_once()
            mock_postgres.connect.assert_called_once()

            # Verify gRPC server was started
            mock_grpc.aio.server.assert_called_once()
            mock_server.start.assert_called_once()

            # Verify health check was set up
            mock_health_servicer.set.assert_called()


class TestBrokerConfig:
    """Tests for Broker Config gRPC methods."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.client = MagicMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        """Create mock PostgreSQL client."""
        mock = MagicMock()
        mock.engine = MagicMock()
        return mock

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock User Repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_broker_config_repo(self) -> AsyncMock:
        """Create mock Broker Config Repository."""
        mock = AsyncMock()
        mock.get_config = AsyncMock(return_value=None)
        mock.set_config = AsyncMock()
        mock.get_all_broker_config = AsyncMock(return_value={})
        mock.is_configured = AsyncMock(return_value=False)
        return mock

    @pytest.fixture
    def mock_executor_client(self) -> AsyncMock:
        """Create mock Executor client."""
        mock = AsyncMock()
        mock.get_account = AsyncMock()
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock gRPC context."""
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_update_broker_config_success(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_broker_config_repo: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should save encrypted broker credentials."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
            broker_config_repository=mock_broker_config_repo,
        )

        request = user_pb2.UpdateBrokerConfigRequest(
            alpaca_api_key="test-api-key",
            alpaca_secret_key="test-secret",
            paper=True,
        )
        response = await servicer.UpdateBrokerConfig(request, mock_context)

        assert response.success is True
        assert mock_broker_config_repo.set_config.call_count == 3  # api_key, secret_key, paper

    @pytest.mark.asyncio
    async def test_update_broker_config_missing_key(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_broker_config_repo: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should reject empty API key."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
            broker_config_repository=mock_broker_config_repo,
        )

        request = user_pb2.UpdateBrokerConfigRequest(
            alpaca_api_key="",
            alpaca_secret_key="test-secret",
        )
        response = await servicer.UpdateBrokerConfig(request, mock_context)

        assert response.success is False
        mock_broker_config_repo.set_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_broker_config_success(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_broker_config_repo: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return decrypted broker credentials."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_broker_config_repo.get_all_broker_config = AsyncMock(
            return_value={
                "alpaca_api_key": "my-key",
                "alpaca_secret_key": "my-secret",
                "alpaca_paper": "true",
            }
        )

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
            broker_config_repository=mock_broker_config_repo,
        )

        request = user_pb2.GetBrokerConfigRequest()
        response = await servicer.GetBrokerConfig(request, mock_context)

        assert response.alpaca_api_key == "my-key"
        assert response.alpaca_secret_key == "my-secret"
        assert response.paper is True
        assert response.configured is True

    @pytest.mark.asyncio
    async def test_get_broker_config_not_configured(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_broker_config_repo: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return configured=False when no keys stored."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_broker_config_repo.get_all_broker_config = AsyncMock(return_value={})

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
            broker_config_repository=mock_broker_config_repo,
        )

        request = user_pb2.GetBrokerConfigRequest()
        response = await servicer.GetBrokerConfig(request, mock_context)

        assert response.configured is False

    @pytest.mark.asyncio
    async def test_get_broker_status_connected(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_broker_config_repo: AsyncMock,
        mock_executor_client: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return connected status with account info."""
        from dataclasses import dataclass

        from shared.generated import user_pb2

        from src.service import UserServicer

        @dataclass
        class MockAccountData:
            cash: float = 50000.0
            buying_power: float = 100000.0
            portfolio_value: float = 75000.0
            equity: float = 75000.0

        mock_broker_config_repo.is_configured = AsyncMock(return_value=True)
        mock_executor_client.get_account = AsyncMock(
            return_value=MockAccountData()
        )

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
            broker_config_repository=mock_broker_config_repo,
            executor_client=mock_executor_client,
        )

        request = user_pb2.GetBrokerStatusRequest()
        response = await servicer.GetBrokerStatus(request, mock_context)

        assert response.configured is True
        assert response.connected is True
        assert response.equity == 75000.0

    @pytest.mark.asyncio
    async def test_get_broker_status_not_configured(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_broker_config_repo: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should return not configured status."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_broker_config_repo.is_configured = AsyncMock(return_value=False)

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
            broker_config_repository=mock_broker_config_repo,
        )

        request = user_pb2.GetBrokerStatusRequest()
        response = await servicer.GetBrokerStatus(request, mock_context)

        assert response.configured is False
        assert response.connected is False


class TestStartTradingBrokerGuard:
    """Tests that StartTrading requires broker config."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        mock = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_postgres(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        mock = AsyncMock()
        mock.update_preferences = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def mock_broker_config_repo(self) -> AsyncMock:
        mock = AsyncMock()
        mock.is_configured = AsyncMock(return_value=False)
        return mock

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        context = MagicMock()
        context.set_code = MagicMock()
        context.set_details = MagicMock()
        return context

    @pytest.mark.asyncio
    async def test_start_trading_blocked_without_broker(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_broker_config_repo: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should reject StartTrading when broker is not configured."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_broker_config_repo.is_configured = AsyncMock(return_value=False)

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
            broker_config_repository=mock_broker_config_repo,
        )

        request = user_pb2.StartTradingRequest(user_id="test-user-id")
        response = await servicer.StartTrading(request, mock_context)

        assert response.success is False
        assert "Alpaca" in response.message
        mock_repository.update_preferences.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_trading_allowed_with_broker(
        self,
        mock_redis: AsyncMock,
        mock_postgres: MagicMock,
        mock_repository: AsyncMock,
        mock_broker_config_repo: AsyncMock,
        mock_context: MagicMock,
    ) -> None:
        """Should allow StartTrading when broker is configured."""
        from shared.generated import user_pb2

        from src.service import UserServicer

        mock_broker_config_repo.is_configured = AsyncMock(return_value=True)

        servicer = UserServicer(
            redis_client=mock_redis,
            postgres_client=mock_postgres,
            repository=mock_repository,
            broker_config_repository=mock_broker_config_repo,
        )

        request = user_pb2.StartTradingRequest(user_id="test-user-id")
        response = await servicer.StartTrading(request, mock_context)

        assert response.success is True
        mock_repository.update_preferences.assert_called_once()
