"""
Unit tests for PostgresClient.

All external dependencies (PostgreSQL) are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.utils.postgres_client import PostgresClient


class TestPostgresClientInit:
    """Tests for PostgresClient initialization."""

    def test_init_with_explicit_url(self) -> None:
        """Should use explicit database URL when provided."""
        url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        client = PostgresClient(database_url=url)
        assert client.database_url == url
        assert client.engine is None
        assert client.session_maker is None

    def test_init_with_database_url_env(self) -> None:
        """Should use DATABASE_URL environment variable."""
        with patch.dict(
            "os.environ",
            {"DATABASE_URL": "postgresql+asyncpg://env:pass@envhost:5432/envdb"},
            clear=True,
        ):
            client = PostgresClient()
            assert client.database_url == "postgresql+asyncpg://env:pass@envhost:5432/envdb"

    def test_init_with_individual_env_vars(self) -> None:
        """Should construct URL from individual POSTGRES_* environment variables."""
        with patch.dict(
            "os.environ",
            {
                "POSTGRES_USER": "testuser",
                "POSTGRES_PASSWORD": "testpass",
                "POSTGRES_HOST": "testhost",
                "POSTGRES_PORT": "5433",
                "POSTGRES_DB": "testdb",
            },
            clear=True,
        ):
            client = PostgresClient()
            assert (
                client.database_url
                == "postgresql+asyncpg://testuser:testpass@testhost:5433/testdb"
            )

    def test_init_with_defaults(self) -> None:
        """Should use default values when no environment variables are set."""
        with patch.dict("os.environ", {}, clear=True):
            client = PostgresClient()
            assert (
                client.database_url
                == "postgresql+asyncpg://postgres:postgres@postgres:5432/bloasis"
            )


class TestPostgresClientConnect:
    """Tests for PostgresClient.connect()."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Should create engine, session maker, and test connection."""
        mock_engine = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_engine.connect = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()))

        with patch(
            "shared.utils.postgres_client.create_async_engine",
            return_value=mock_engine,
        ):
            with patch("shared.utils.postgres_client.async_sessionmaker") as mock_sessionmaker:
                client = PostgresClient(
                    database_url="postgresql+asyncpg://user:pass@localhost:5432/testdb"
                )
                await client.connect()

                assert client.engine is mock_engine
                assert client.session_maker is mock_sessionmaker.return_value

    @pytest.mark.asyncio
    async def test_connect_failure(self) -> None:
        """Should raise ConnectionError on failure."""
        with patch(
            "shared.utils.postgres_client.create_async_engine",
            side_effect=Exception("Connection refused"),
        ):
            client = PostgresClient(
                database_url="postgresql+asyncpg://user:pass@localhost:5432/testdb"
            )

            with pytest.raises(ConnectionError) as exc_info:
                await client.connect()

            assert "Failed to connect to PostgreSQL" in str(exc_info.value)


class TestPostgresClientClose:
    """Tests for PostgresClient.close()."""

    @pytest.mark.asyncio
    async def test_close_connected_client(self) -> None:
        """Should dispose engine and reset state."""
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        client = PostgresClient(
            database_url="postgresql+asyncpg://user:pass@localhost:5432/testdb"
        )
        client.engine = mock_engine
        client.session_maker = MagicMock()

        await client.close()

        mock_engine.dispose.assert_called_once()
        assert client.engine is None
        assert client.session_maker is None

    @pytest.mark.asyncio
    async def test_close_not_connected(self) -> None:
        """Should handle close when not connected."""
        client = PostgresClient()
        client.engine = None
        client.session_maker = None

        await client.close()  # Should not raise

        assert client.engine is None
        assert client.session_maker is None


class TestPostgresClientGetSession:
    """Tests for PostgresClient.get_session()."""

    @pytest.mark.asyncio
    async def test_get_session_not_connected(self) -> None:
        """Should raise ConnectionError if not connected."""
        client = PostgresClient()

        with pytest.raises(ConnectionError) as exc_info:
            async with client.get_session():
                pass

        assert "not connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_session_success(self) -> None:
        """Should yield a session and commit on success."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=None),
        )

        client = PostgresClient()
        client.session_maker = mock_session_maker

        async with client.get_session() as session:
            assert session is mock_session

        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_session_rollback_on_error(self) -> None:
        """Should rollback session on exception."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=None),
        )

        client = PostgresClient()
        client.session_maker = mock_session_maker

        with pytest.raises(ValueError):
            async with client.get_session():
                raise ValueError("Test error")

        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()


class TestPostgresClientExecuteQuery:
    """Tests for PostgresClient.execute_query()."""

    @pytest.mark.asyncio
    async def test_execute_query_not_connected(self) -> None:
        """Should raise ConnectionError if not connected."""
        client = PostgresClient()

        with pytest.raises(ConnectionError) as exc_info:
            await client.execute_query("SELECT 1")

        assert "not connected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_query_success(self) -> None:
        """Should execute query and return results."""
        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[("row1",), ("row2",)])

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=None),
        )

        client = PostgresClient()
        client.session_maker = mock_session_maker

        result = await client.execute_query("SELECT * FROM users")

        assert result == [("row1",), ("row2",)]
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_with_params(self) -> None:
        """Should execute query with parameters."""
        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[("user1",)])

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_session_maker = MagicMock()
        mock_session_maker.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=None),
        )

        client = PostgresClient()
        client.session_maker = mock_session_maker

        result = await client.execute_query(
            "SELECT * FROM users WHERE id = :user_id",
            {"user_id": "123"},
        )

        assert result == [("user1",)]
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_failure(self) -> None:
        """Should raise RuntimeError on query failure."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("Query failed"))

        mock_session_maker = MagicMock()
        mock_session_maker.return_value = AsyncMock(
            __aenter__=AsyncMock(return_value=mock_session),
            __aexit__=AsyncMock(return_value=None),
        )

        client = PostgresClient()
        client.session_maker = mock_session_maker

        with pytest.raises(RuntimeError) as exc_info:
            await client.execute_query("INVALID SQL")

        assert "Failed to execute query" in str(exc_info.value)


class TestPostgresClientExtractHostInfo:
    """Tests for PostgresClient._extract_host_info()."""

    def test_extract_host_info_standard_url(self) -> None:
        """Should extract host:port from standard URL."""
        client = PostgresClient(
            database_url="postgresql+asyncpg://user:pass@localhost:5432/testdb"
        )
        assert client._extract_host_info() == "localhost:5432"

    def test_extract_host_info_without_port(self) -> None:
        """Should handle URL without explicit port."""
        client = PostgresClient(
            database_url="postgresql+asyncpg://user:pass@dbhost/testdb"
        )
        assert client._extract_host_info() == "dbhost"

    def test_extract_host_info_invalid_url(self) -> None:
        """Should return 'unknown' for invalid URL format."""
        client = PostgresClient(database_url="invalid_url")
        assert client._extract_host_info() == "unknown"
