"""
PostgreSQL client utility for BLOASIS services.

Provides async PostgreSQL operations using SQLAlchemy with asyncpg dialect.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


class PostgresClient:
    """
    Async PostgreSQL client for database operations.

    Uses environment variables for configuration:
    - DATABASE_URL: Full database URL (takes precedence)
    - POSTGRES_USER: Database username (default: 'postgres')
    - POSTGRES_PASSWORD: Database password (default: 'postgres')
    - POSTGRES_HOST: Database hostname (default: 'postgres')
    - POSTGRES_PORT: Database port (default: 5432)
    - POSTGRES_DB: Database name (default: 'bloasis')

    Example:
        client = PostgresClient()
        await client.connect()
        async with client.get_session() as session:
            result = await session.execute(text("SELECT 1"))
        await client.close()
    """

    def __init__(self, database_url: Optional[str] = None) -> None:
        """
        Initialize PostgreSQL client configuration.

        Args:
            database_url: Full database URL. If not provided, constructs from
                          individual POSTGRES_* environment variables.
        """
        if database_url is not None:
            self.database_url: str = database_url
        else:
            env_url = os.getenv("DATABASE_URL")
            if env_url:
                self.database_url = env_url
            else:
                user = os.getenv("POSTGRES_USER") or "postgres"
                password = os.getenv("POSTGRES_PASSWORD") or "postgres"
                host = os.getenv("POSTGRES_HOST") or "postgres"
                port = os.getenv("POSTGRES_PORT") or "5432"
                db = os.getenv("POSTGRES_DB") or "bloasis"
                self.database_url = (
                    f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
                )

        self.engine: Optional[AsyncEngine] = None
        self.session_maker: Optional[async_sessionmaker[AsyncSession]] = None

    async def connect(self) -> None:
        """
        Establish connection to PostgreSQL server.

        Creates an async SQLAlchemy engine and session maker,
        then tests the connection.

        Raises:
            ConnectionError: If connection to PostgreSQL fails.
        """
        try:
            self.engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_pre_ping=True,
            )
            self.session_maker = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # Test the connection
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

            # Extract host info for logging (without credentials)
            host_info = self._extract_host_info()
            logger.info(
                "Connected to PostgreSQL",
                extra={"host": host_info},
            )

        except Exception as e:
            host_info = self._extract_host_info()
            logger.error(
                "PostgreSQL connection failed",
                extra={"host": host_info, "error": str(e)},
            )
            raise ConnectionError(
                f"Failed to connect to PostgreSQL at {host_info}: {e}"
            ) from e

    async def close(self) -> None:
        """
        Close the PostgreSQL connection and dispose of the engine.

        Cleans up all connection pool resources.
        """
        if self.engine is not None:
            await self.engine.dispose()
            host_info = self._extract_host_info()
            self.engine = None
            self.session_maker = None
            logger.info(
                "Disconnected from PostgreSQL",
                extra={"host": host_info},
            )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session as a context manager.

        Yields:
            AsyncSession: An async SQLAlchemy session for database operations.

        Raises:
            ConnectionError: If not connected to PostgreSQL.

        Example:
            async with client.get_session() as session:
                result = await session.execute(text("SELECT * FROM users"))
                rows = result.fetchall()
        """
        if self.session_maker is None:
            raise ConnectionError(
                "PostgreSQL client is not connected. Call connect() first."
            )

        async with self.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def execute_query(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Sequence[Any]:
        """
        Execute a raw SQL query with parameters.

        Args:
            query: The SQL query string. Use :param_name for parameters.
            params: Optional dictionary of query parameters.

        Returns:
            Sequence of result rows.

        Raises:
            ConnectionError: If not connected to PostgreSQL.
            RuntimeError: If query execution fails.

        Example:
            result = await client.execute_query(
                "SELECT * FROM users WHERE id = :user_id",
                {"user_id": "123"}
            )
        """
        if self.session_maker is None:
            raise ConnectionError(
                "PostgreSQL client is not connected. Call connect() first."
            )

        try:
            async with self.session_maker() as session:
                stmt = text(query)
                if params:
                    stmt = stmt.bindparams(**params)
                result: Result[Any] = await session.execute(stmt)
                rows = result.fetchall()
                await session.commit()
                logger.debug(
                    "Query executed",
                    extra={"query_length": len(query), "row_count": len(rows)},
                )
                return rows
        except Exception as e:
            logger.error(
                "Query execution failed",
                extra={"error": str(e)},
            )
            raise RuntimeError(f"Failed to execute query: {e}") from e

    def _extract_host_info(self) -> str:
        """
        Extract host information from database URL for logging.

        Returns:
            Host and port string without credentials.
        """
        try:
            # Parse URL to extract host:port without credentials
            # Format: postgresql+asyncpg://user:pass@host:port/db
            url = self.database_url
            if "@" in url:
                after_at = url.split("@", 1)[1]
                if "/" in after_at:
                    host_port = after_at.split("/", 1)[0]
                else:
                    host_port = after_at
                return host_port
            return "unknown"
        except Exception:
            return "unknown"
