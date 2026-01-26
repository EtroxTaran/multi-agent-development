"""Tests for database connection and connection pool.

Tests the Connection class, ConnectionPool, and related utilities
from orchestrator.db.connection module.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.db.connection import (
    Connection,
    ConnectionError,
    ConnectionPool,
    ConnectionStats,
    QueryError,
    get_connection,
    get_pool,
)


class TestConnection:
    """Tests for the Connection class."""

    @pytest.fixture
    def connection(self, mock_surreal_config):
        """Create a Connection instance for testing."""
        return Connection(mock_surreal_config, "test_db")

    def test_connection_init(self, connection, mock_surreal_config):
        """Test Connection initialization."""
        assert connection.config == mock_surreal_config
        assert connection.database == "test_db"
        assert connection._client is None
        assert connection._connected is False

    def test_is_connected_false_when_no_client(self, connection):
        """Test is_connected returns False when no client."""
        assert connection.is_connected is False

    def test_is_connected_false_when_not_connected(self, connection, mock_surreal_client):
        """Test is_connected returns False when client exists but not connected."""
        connection._client = mock_surreal_client
        connection._connected = False
        assert connection.is_connected is False

    def test_is_connected_true_when_connected(self, connection, mock_surreal_client):
        """Test is_connected returns True when properly connected."""
        connection._client = mock_surreal_client
        connection._connected = True
        assert connection.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_success_local(self, connection, mock_surreal_client):
        """Test successful connection to local SurrealDB (ws://)."""
        with patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client):
            await connection.connect()

            assert connection.is_connected is True
            mock_surreal_client.connect.assert_called_once()
            mock_surreal_client.signin.assert_called_once()
            mock_surreal_client.use.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, connection, mock_surreal_client):
        """Test connect() does nothing if already connected."""
        connection._connected = True
        connection._client = mock_surreal_client

        await connection.connect()

        # Should not try to connect again
        mock_surreal_client.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_timeout(self, connection, mock_surreal_client):
        """Test connection timeout handling."""
        mock_surreal_client.connect = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client):
            with pytest.raises(ConnectionError, match="timeout"):
                await connection.connect()

    @pytest.mark.asyncio
    async def test_connect_failure(self, connection, mock_surreal_client):
        """Test connection failure handling."""
        mock_surreal_client.connect = AsyncMock(side_effect=Exception("Network error"))

        with patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client):
            with pytest.raises(ConnectionError, match="Failed to connect"):
                await connection.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_connection, mock_surreal_client):
        """Test disconnect closes client properly."""
        await mock_connection.disconnect()

        mock_surreal_client.close.assert_called_once()
        assert mock_connection._client is None
        assert mock_connection._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_handles_close_error(self, mock_connection, mock_surreal_client):
        """Test disconnect handles close errors gracefully."""
        mock_surreal_client.close = AsyncMock(side_effect=Exception("Close error"))

        # Should not raise
        await mock_connection.disconnect()

        assert mock_connection._client is None
        assert mock_connection._connected is False

    @pytest.mark.asyncio
    async def test_query_success(self, mock_connection, mock_surreal_client):
        """Test successful query execution."""
        mock_surreal_client.query = AsyncMock(
            return_value=[{"result": [{"id": "test:1", "name": "Test"}]}]
        )

        result = await mock_connection.query("SELECT * FROM test")

        assert result == [{"id": "test:1", "name": "Test"}]

    @pytest.mark.asyncio
    async def test_query_with_params(self, mock_connection, mock_surreal_client):
        """Test query with parameters."""
        mock_surreal_client.query = AsyncMock(return_value=[{"result": []}])

        await mock_connection.query("SELECT * FROM test WHERE id = $id", {"id": "test:1"})

        mock_surreal_client.query.assert_called_once_with(
            "SELECT * FROM test WHERE id = $id", {"id": "test:1"}
        )

    @pytest.mark.asyncio
    async def test_query_connects_if_not_connected(self, connection, mock_surreal_client):
        """Test query auto-connects if not connected."""
        mock_surreal_client.query = AsyncMock(return_value=[{"result": []}])

        with patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client):
            await connection.query("SELECT * FROM test")

        mock_surreal_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_timeout(self, mock_connection, mock_surreal_client):
        """Test query timeout handling."""
        mock_surreal_client.query = AsyncMock(side_effect=asyncio.TimeoutError())

        with pytest.raises(QueryError, match="timeout"):
            await mock_connection.query("SELECT * FROM test")

    @pytest.mark.asyncio
    async def test_query_failure(self, mock_connection, mock_surreal_client):
        """Test query failure handling."""
        mock_surreal_client.query = AsyncMock(side_effect=Exception("Query failed"))

        with pytest.raises(QueryError, match="failed"):
            await mock_connection.query("SELECT * FROM test")

    @pytest.mark.asyncio
    async def test_create_success(self, mock_connection, mock_surreal_client):
        """Test successful record creation."""
        mock_surreal_client.create = AsyncMock(return_value={"id": "test:123", "name": "Test"})

        result = await mock_connection.create("test", {"name": "Test"})

        assert result["id"] == "test:123"
        assert result["name"] == "Test"

    @pytest.mark.asyncio
    async def test_create_with_id(self, mock_connection, mock_surreal_client):
        """Test record creation with specific ID."""
        mock_surreal_client.create = AsyncMock(return_value={"id": "test:custom"})

        await mock_connection.create("test", {"name": "Test"}, record_id="custom")

        mock_surreal_client.create.assert_called_once_with("test:custom", {"name": "Test"})

    @pytest.mark.asyncio
    async def test_create_with_special_id(self, mock_connection, mock_surreal_client):
        """Test record creation with ID containing special characters."""
        mock_surreal_client.create = AsyncMock(return_value={"id": "test:`my-id`"})

        await mock_connection.create("test", {"name": "Test"}, record_id="my-id")

        # IDs with hyphens should be escaped with backticks
        mock_surreal_client.create.assert_called_once_with("test:`my-id`", {"name": "Test"})

    @pytest.mark.asyncio
    async def test_select_success(self, mock_connection, mock_surreal_client):
        """Test successful record selection."""
        mock_surreal_client.select = AsyncMock(return_value=[{"id": "test:1"}, {"id": "test:2"}])

        result = await mock_connection.select("test")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_select_single_record(self, mock_connection, mock_surreal_client):
        """Test selecting a single record."""
        mock_surreal_client.select = AsyncMock(return_value={"id": "test:1"})

        result = await mock_connection.select("test:1")

        assert result == [{"id": "test:1"}]

    @pytest.mark.asyncio
    async def test_update_success(self, mock_connection, mock_surreal_client):
        """Test successful record update."""
        mock_surreal_client.update = AsyncMock(return_value={"id": "test:1", "name": "Updated"})

        result = await mock_connection.update("test:1", {"name": "Updated"})

        assert result["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_connection, mock_surreal_client):
        """Test successful record deletion."""
        mock_surreal_client.delete = AsyncMock()

        result = await mock_connection.delete("test:1")

        assert result is True

    @pytest.mark.asyncio
    async def test_live_query(self, mock_connection, mock_surreal_client):
        """Test live query subscription."""

        def callback(data):
            pass

        result = await mock_connection.live("test", callback)

        assert result == "live-query-uuid"
        mock_surreal_client.live.assert_called_once_with("test", callback)

    @pytest.mark.asyncio
    async def test_kill_live_query(self, mock_connection, mock_surreal_client):
        """Test stopping a live query."""
        await mock_connection.kill("live-query-uuid")

        mock_surreal_client.kill.assert_called_once_with("live-query-uuid")


class TestConnectionPool:
    """Tests for the ConnectionPool class."""

    @pytest.fixture
    def pool(self, mock_surreal_config):
        """Create a ConnectionPool instance for testing."""
        return ConnectionPool(mock_surreal_config, "test_db")

    def test_pool_init(self, pool, mock_surreal_config):
        """Test ConnectionPool initialization."""
        assert pool.config == mock_surreal_config
        assert pool.database == "test_db"
        assert pool._initialized is False

    def test_pool_stats_initial(self, pool):
        """Test initial pool statistics."""
        stats = pool.stats
        assert stats.total_connections == 0
        assert stats.active_connections == 0
        assert stats.failed_connections == 0

    @pytest.mark.asyncio
    async def test_pool_initialize(self, pool, mock_surreal_client):
        """Test pool initialization creates connections."""
        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test_db",
            ),
        ):
            await pool.initialize()

            assert pool._initialized is True
            assert len(pool._connections) == pool.config.pool_size

    @pytest.mark.asyncio
    async def test_pool_initialize_partial_failure(self, pool, mock_surreal_client):
        """Test pool initialization with some connection failures."""
        call_count = 0

        async def connect_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ConnectionError("Connection failed")

        mock_surreal_client.connect = AsyncMock(side_effect=connect_side_effect)

        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test_db",
            ),
        ):
            await pool.initialize()

            # Should still initialize with remaining connections
            assert pool._initialized is True
            assert pool.stats.failed_connections == 1

    @pytest.mark.asyncio
    async def test_pool_initialize_all_fail(self, pool, mock_surreal_client):
        """Test pool initialization fails if all connections fail."""
        mock_surreal_client.connect = AsyncMock(side_effect=ConnectionError("Connection failed"))

        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test_db",
            ),
        ):
            with pytest.raises(ConnectionError, match="Failed to create any connections"):
                await pool.initialize()

    @pytest.mark.asyncio
    async def test_pool_acquire_and_release(self, pool, mock_surreal_client):
        """Test acquiring and releasing connections from pool."""
        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test_db",
            ),
        ):
            await pool.initialize()

            async with pool.acquire() as conn:
                assert pool.stats.active_connections == 1
                assert conn is not None

            assert pool.stats.active_connections == 0

    @pytest.mark.asyncio
    async def test_pool_auto_initialize(self, pool, mock_surreal_client):
        """Test pool auto-initializes on first acquire."""
        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test_db",
            ),
        ):
            async with pool.acquire() as _conn:
                assert pool._initialized is True

    @pytest.mark.asyncio
    async def test_pool_reconnect_on_acquire(self, pool, mock_surreal_client):
        """Test pool reconnects disconnected connections."""
        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test_db",
            ),
        ):
            await pool.initialize()

            # Simulate disconnection
            for conn in pool._connections:
                conn._connected = False

            async with pool.acquire() as conn:
                # Should reconnect
                assert conn.is_connected

    @pytest.mark.asyncio
    async def test_pool_execute(self, pool, mock_surreal_client):
        """Test executing queries through the pool."""
        mock_surreal_client.query = AsyncMock(return_value=[{"result": [{"id": "test:1"}]}])

        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test_db",
            ),
        ):
            await pool.initialize()
            result = await pool.execute("SELECT * FROM test")

            assert result == [{"id": "test:1"}]
            assert pool.stats.total_queries == 1

    @pytest.mark.asyncio
    async def test_pool_execute_tracks_failed_queries(self, pool, mock_surreal_client):
        """Test pool tracks failed queries in stats."""
        mock_surreal_client.query = AsyncMock(side_effect=asyncio.TimeoutError())

        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test_db",
            ),
        ):
            await pool.initialize()

            with pytest.raises(QueryError):
                await pool.execute("SELECT * FROM test")

            assert pool.stats.failed_queries == 1

    @pytest.mark.asyncio
    async def test_pool_close(self, pool, mock_surreal_client):
        """Test closing the pool."""
        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test_db",
            ),
        ):
            await pool.initialize()
            await pool.close()

            assert pool._initialized is False
            assert len(pool._connections) == 0


class TestConnectionStats:
    """Tests for ConnectionStats dataclass."""

    def test_stats_defaults(self):
        """Test default values."""
        stats = ConnectionStats()
        assert stats.total_connections == 0
        assert stats.active_connections == 0
        assert stats.failed_connections == 0
        assert stats.total_queries == 0
        assert stats.failed_queries == 0
        assert stats.last_connected is None
        assert stats.last_error is None

    def test_stats_with_values(self, connection_stats):
        """Test stats with actual values."""
        assert connection_stats.total_connections == 5
        assert connection_stats.active_connections == 2
        assert connection_stats.total_queries == 100
        assert connection_stats.failed_queries == 3


class TestGetConnection:
    """Tests for get_connection context manager."""

    @pytest.mark.asyncio
    async def test_get_connection_returns_connection(self, mock_surreal_client):
        """Test get_connection returns a working connection."""
        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test",
            ),
            patch("orchestrator.db.connection._pools", {}),
        ):
            async with get_connection("test") as conn:
                assert conn is not None


class TestGetPool:
    """Tests for get_pool function."""

    @pytest.mark.asyncio
    async def test_get_pool_creates_new_pool(self, mock_surreal_client):
        """Test get_pool creates a new pool if none exists."""
        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test",
            ),
            patch("orchestrator.db.connection._pools", {}),
        ):
            pool = await get_pool("test")
            assert pool is not None
            assert pool._initialized

    @pytest.mark.asyncio
    async def test_get_pool_reuses_existing_pool(self, mock_surreal_client):
        """Test get_pool reuses existing pool for same project."""
        with (
            patch("orchestrator.db.connection.AsyncSurreal", return_value=mock_surreal_client),
            patch(
                "orchestrator.db.connection.get_project_database",
                return_value="project_test",
            ),
            patch("orchestrator.db.connection._pools", {}),
        ):
            pool1 = await get_pool("test")
            pool2 = await get_pool("test")

            # Same event loop, same db = same pool
            assert pool1 is pool2
