"""
User Service - gRPC Servicer Implementation.

Implements the UserService gRPC interface with:
- Redis caching (1-hour TTL for user preferences)
- PostgreSQL persistence via Repository pattern
- bcrypt password hashing
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import grpc
from shared.generated import user_pb2, user_pb2_grpc
from shared.utils import PostgresClient, RedisClient

from .models import (
    User,
    UserPreferences,
    cache_dict_to_preferences,
    preferences_to_cache_dict,
)
from .repositories import UserRepository

logger = logging.getLogger(__name__)

# Cache configuration (user-specific caching - Tier 3)
CACHE_TTL = 3600  # 1 hour in seconds


def _preferences_cache_key(user_id: str) -> str:
    """Generate cache key for user preferences."""
    return f"user:{user_id}:preferences"


def _user_to_proto(user: User) -> user_pb2.User:
    """
    Convert a User domain object to proto message.

    Args:
        user: User domain object.

    Returns:
        User proto message.
    """
    return user_pb2.User(
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _preferences_to_proto(preferences: UserPreferences) -> user_pb2.UserPreferences:
    """
    Convert a UserPreferences domain object to proto message.

    Args:
        preferences: UserPreferences domain object.

    Returns:
        UserPreferences proto message.
    """
    return user_pb2.UserPreferences(
        user_id=preferences.user_id,
        risk_profile=preferences.risk_profile,
        max_portfolio_risk=str(preferences.max_portfolio_risk),
        max_position_size=str(preferences.max_position_size),
        preferred_sectors=preferences.preferred_sectors,
        enable_notifications=preferences.enable_notifications,
        trading_enabled=preferences.trading_enabled,
    )


class UserServicer(user_pb2_grpc.UserServiceServicer):
    """
    gRPC servicer implementing the UserService interface.

    Provides user account management and preferences.
    Preferences are cached for 1 hour (user-specific data).
    """

    def __init__(
        self,
        redis_client: Optional[RedisClient] = None,
        postgres_client: Optional[PostgresClient] = None,
        repository: Optional[UserRepository] = None,
        redpanda_client=None,
    ) -> None:
        """
        Initialize the servicer with required clients.

        Args:
            redis_client: Redis client for caching.
            postgres_client: PostgreSQL client for persistence.
            repository: Repository for database operations.
            redpanda_client: Redpanda client for event publishing.
        """
        self.redis = redis_client
        self.postgres = postgres_client
        self.repository = repository or UserRepository(postgres_client)
        self.redpanda = redpanda_client

    async def GetUser(
        self,
        request: user_pb2.GetUserRequest,
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.GetUserResponse:
        """
        Get a user by ID.

        Args:
            request: The gRPC request containing user_id.
            context: The gRPC servicer context.

        Returns:
            GetUserResponse with user data.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return user_pb2.GetUserResponse()

            user = await self.repository.get_user_by_id(user_id)
            if not user:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"User {user_id} not found")
                return user_pb2.GetUserResponse()

            return user_pb2.GetUserResponse(user=_user_to_proto(user))

        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get user: {str(e)}")
            return user_pb2.GetUserResponse()

    async def CreateUser(
        self,
        request: user_pb2.CreateUserRequest,
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.CreateUserResponse:
        """
        Create a new user account.

        Args:
            request: The gRPC request containing email, password, and name.
            context: The gRPC servicer context.

        Returns:
            CreateUserResponse with created user data.
        """
        try:
            email = request.email
            password = request.password
            name = request.name

            if not email:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("email is required")
                return user_pb2.CreateUserResponse()

            if not password:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("password is required")
                return user_pb2.CreateUserResponse()

            if not name:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("name is required")
                return user_pb2.CreateUserResponse()

            # Validate email format (basic check)
            if "@" not in email or "." not in email:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Invalid email format")
                return user_pb2.CreateUserResponse()

            # Validate password length
            if len(password) < 8:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Password must be at least 8 characters")
                return user_pb2.CreateUserResponse()

            user = await self.repository.create_user(email, password, name)

            logger.info(f"Created user: {user.user_id}")
            return user_pb2.CreateUserResponse(
                user_id=user.user_id,
                user=_user_to_proto(user),
            )

        except ValueError as e:
            logger.warning(f"Failed to create user: {e}")
            context.set_code(grpc.StatusCode.ALREADY_EXISTS)
            context.set_details(str(e))
            return user_pb2.CreateUserResponse()
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to create user: {str(e)}")
            return user_pb2.CreateUserResponse()

    async def ValidateCredentials(
        self,
        request: user_pb2.ValidateCredentialsRequest,
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.ValidateCredentialsResponse:
        """
        Validate user credentials (internal use by Auth Service).

        Args:
            request: The gRPC request containing email and password.
            context: The gRPC servicer context.

        Returns:
            ValidateCredentialsResponse with validation result.
        """
        try:
            email = request.email
            password = request.password

            if not email or not password:
                return user_pb2.ValidateCredentialsResponse(valid=False, user_id="")

            valid, user_id = await self.repository.validate_credentials(email, password)

            return user_pb2.ValidateCredentialsResponse(
                valid=valid,
                user_id=user_id or "",
            )

        except Exception as e:
            logger.error(f"Failed to validate credentials: {e}")
            return user_pb2.ValidateCredentialsResponse(valid=False, user_id="")

    async def GetUserPreferences(
        self,
        request: user_pb2.GetPreferencesRequest,
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.GetPreferencesResponse:
        """
        Get user trading preferences.

        Implements caching strategy:
        1. Check Redis cache
        2. If cache miss, query database via repository
        3. Cache the result for 1 hour

        Args:
            request: The gRPC request containing user_id.
            context: The gRPC servicer context.

        Returns:
            GetPreferencesResponse with preferences data.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return user_pb2.GetPreferencesResponse()

            cache_key = _preferences_cache_key(user_id)

            # Check cache first
            if self.redis:
                cached = await self.redis.get(cache_key)
                if cached and isinstance(cached, dict):
                    logger.info(f"Cache hit for preferences: {user_id}")
                    preferences = cache_dict_to_preferences(cached)
                    return user_pb2.GetPreferencesResponse(
                        preferences=_preferences_to_proto(preferences)
                    )

            # Cache miss - query database
            logger.info(f"Cache miss for preferences: {user_id}")
            preferences = await self.repository.get_preferences(user_id)

            if not preferences:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Preferences for user {user_id} not found")
                return user_pb2.GetPreferencesResponse()

            # Cache the result
            if self.redis:
                cache_data = preferences_to_cache_dict(preferences)
                await self.redis.setex(cache_key, CACHE_TTL, cache_data)
                logger.info(f"Cached preferences for user {user_id} with TTL {CACHE_TTL}s")

            return user_pb2.GetPreferencesResponse(
                preferences=_preferences_to_proto(preferences)
            )

        except Exception as e:
            logger.error(f"Failed to get preferences: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get preferences: {str(e)}")
            return user_pb2.GetPreferencesResponse()

    async def UpdateUserPreferences(
        self,
        request: user_pb2.UpdatePreferencesRequest,
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.UpdatePreferencesResponse:
        """
        Update user trading preferences.

        Invalidates cache after update.

        Args:
            request: The gRPC request containing user_id and preferences.
            context: The gRPC servicer context.

        Returns:
            UpdatePreferencesResponse with updated preferences.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return user_pb2.UpdatePreferencesResponse()

            prefs = request.preferences
            if not prefs:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("preferences is required")
                return user_pb2.UpdatePreferencesResponse()

            # Parse values from request
            # Note: For scalar fields in proto3, we can't distinguish between "not set" and "default value"
            # So we only pass non-empty/non-default values
            risk_profile = prefs.risk_profile if prefs.risk_profile else None
            max_portfolio_risk = (
                Decimal(prefs.max_portfolio_risk) if prefs.max_portfolio_risk else None
            )
            max_position_size = (
                Decimal(prefs.max_position_size) if prefs.max_position_size else None
            )
            preferred_sectors = list(prefs.preferred_sectors) if prefs.preferred_sectors else None
            # For boolean fields, we pass None to indicate "not updated" only when the
            # request explicitly does not include it (using presence tracking via wrapper)
            # Since proto3 doesn't support presence for scalar bools, we always pass the value
            # This means enable_notifications will always be set to whatever value is in the request
            enable_notifications: bool | None = None
            # Check if any fields are being updated - if not, this might be an update to enable_notifications
            if (
                risk_profile is None
                and max_portfolio_risk is None
                and max_position_size is None
                and preferred_sectors is None
            ):
                # If nothing else is set, assume enable_notifications is being updated
                enable_notifications = prefs.enable_notifications
            elif prefs.enable_notifications is not None:
                # For explicit updates, include enable_notifications value
                enable_notifications = prefs.enable_notifications

            # Update preferences
            updated = await self.repository.update_preferences(
                user_id=user_id,
                risk_profile=risk_profile,
                max_portfolio_risk=max_portfolio_risk,
                max_position_size=max_position_size,
                preferred_sectors=preferred_sectors,
                enable_notifications=enable_notifications,
            )

            if not updated:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Preferences for user {user_id} not found")
                return user_pb2.UpdatePreferencesResponse()

            # Invalidate cache
            await self._invalidate_cache(user_id)

            logger.info(f"Updated preferences for user {user_id}")
            return user_pb2.UpdatePreferencesResponse(
                preferences=_preferences_to_proto(updated)
            )

        except ValueError as e:
            logger.warning(f"Invalid preferences update: {e}")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return user_pb2.UpdatePreferencesResponse()
        except Exception as e:
            logger.error(f"Failed to update preferences: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to update preferences: {str(e)}")
            return user_pb2.UpdatePreferencesResponse()

    async def _invalidate_cache(self, user_id: str) -> None:
        """
        Invalidate cache for a user after write operations.

        Args:
            user_id: User identifier whose cache should be invalidated.
        """
        if self.redis:
            await self.redis.delete(_preferences_cache_key(user_id))
            logger.info(f"Invalidated cache for user {user_id}")

    async def StartTrading(
        self,
        request: user_pb2.StartTradingRequest,
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.StartTradingResponse:
        """
        Start AI auto-trading for a user.

        Updates database, invalidates cache, and publishes trading-control event.

        Args:
            request: The gRPC request containing user_id.
            context: The gRPC servicer context.

        Returns:
            StartTradingResponse with success status.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return user_pb2.StartTradingResponse(
                    success=False,
                    message="user_id is required",
                    timestamp="",
                )

            # Update preferences to enable trading
            updated = await self.repository.update_preferences(
                user_id=user_id,
                trading_enabled=True,
            )

            if not updated:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"User {user_id} not found")
                return user_pb2.StartTradingResponse(
                    success=False,
                    message=f"User {user_id} not found",
                    timestamp="",
                )

            # Invalidate cache
            await self._invalidate_cache(user_id)

            # Publish Redpanda event
            if self.redpanda:
                event = {
                    "event_id": str(uuid4()),
                    "timestamp": datetime.utcnow().isoformat(),
                    "user_id": user_id,
                    "action": "started",
                    "stop_mode": "",
                }
                await self.redpanda.publish("trading-control-events", event)

            timestamp = datetime.utcnow().isoformat()
            logger.info(f"AI trading started for user {user_id}")
            return user_pb2.StartTradingResponse(
                success=True,
                message="AI trading started successfully",
                timestamp=timestamp,
            )

        except Exception as e:
            logger.error(f"Failed to start trading: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return user_pb2.StartTradingResponse(
                success=False,
                message="Internal error occurred",
                timestamp="",
            )

    async def StopTrading(
        self,
        request: user_pb2.StopTradingRequest,
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.StopTradingResponse:
        """
        Stop AI auto-trading for a user.

        Supports two modes:
        - soft: Allows protective orders to complete before stopping
        - hard: Immediately cancels all pending orders

        Args:
            request: The gRPC request containing user_id and stop_mode.
            context: The gRPC servicer context.

        Returns:
            StopTradingResponse with success status and cancellation count.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return user_pb2.StopTradingResponse(
                    success=False,
                    message="user_id is required",
                    orders_cancelled=0,
                    timestamp="",
                )

            stop_mode = request.stop_mode or "soft"

            # Validate stop_mode
            if stop_mode not in ["hard", "soft"]:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("stop_mode must be 'hard' or 'soft'")
                return user_pb2.StopTradingResponse(
                    success=False,
                    message="stop_mode must be 'hard' or 'soft'",
                    orders_cancelled=0,
                    timestamp="",
                )

            # Update preferences to disable trading
            updated = await self.repository.update_preferences(
                user_id=user_id,
                trading_enabled=False,
            )

            if not updated:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"User {user_id} not found")
                return user_pb2.StopTradingResponse(
                    success=False,
                    message=f"User {user_id} not found",
                    orders_cancelled=0,
                    timestamp="",
                )

            # Invalidate cache
            await self._invalidate_cache(user_id)

            # Publish Redpanda event (Executor Service will handle order cancellation)
            if self.redpanda:
                event = {
                    "event_id": str(uuid4()),
                    "timestamp": datetime.utcnow().isoformat(),
                    "user_id": user_id,
                    "action": "stopped",
                    "stop_mode": stop_mode,
                }
                await self.redpanda.publish("trading-control-events", event)

            message = (
                "AI trading stopped immediately (hard stop)"
                if stop_mode == "hard"
                else "AI trading will stop after current positions are protected (soft stop)"
            )
            timestamp = datetime.utcnow().isoformat()

            logger.info(f"AI trading stopped for user {user_id} (mode: {stop_mode})")
            return user_pb2.StopTradingResponse(
                success=True,
                message=message,
                orders_cancelled=0,  # Executor Service updates this
                timestamp=timestamp,
            )

        except Exception as e:
            logger.error(f"Failed to stop trading: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            return user_pb2.StopTradingResponse(
                success=False,
                message="Internal error occurred",
                orders_cancelled=0,
                timestamp="",
            )

    async def GetTradingStatus(
        self,
        request: user_pb2.GetTradingStatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.GetTradingStatusResponse:
        """
        Get trading status for a user.

        Args:
            request: The gRPC request containing user_id.
            context: The gRPC servicer context.

        Returns:
            GetTradingStatusResponse with trading status.
        """
        try:
            user_id = request.user_id
            if not user_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("user_id is required")
                return user_pb2.GetTradingStatusResponse()

            preferences = await self.repository.get_preferences(user_id)

            if not preferences:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Preferences for user {user_id} not found")
                return user_pb2.GetTradingStatusResponse()

            status = "active" if preferences.trading_enabled else "inactive"
            last_changed = preferences.updated_at.isoformat() if preferences.updated_at else ""
            next_poll_ms = 3000 if preferences.trading_enabled else 10000

            return user_pb2.GetTradingStatusResponse(
                trading_enabled=preferences.trading_enabled,
                status=status,
                last_changed=last_changed,
                next_poll_ms=next_poll_ms,
            )

        except Exception as e:
            logger.error(f"Failed to get trading status: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get trading status: {str(e)}")
            return user_pb2.GetTradingStatusResponse()
