"""SurrealDB connection management.

Provides async connection pooling, automatic reconnection,
and context managers for database operations.
"""

import asyncio
import logging
import ssl
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Union

import requests
import websockets
from surrealdb import AsyncSurreal
from surrealdb.connections.async_ws import AsyncWsSurrealConnection

from .config import SurrealConfig, get_config, get_project_database

logger = logging.getLogger(__name__)


class InsecureAsyncWsSurrealConnection(AsyncWsSurrealConnection):
    """Custom connection that allows skipping SSL verification."""

    async def connect(self, url: Optional[str] = None) -> None:
        """Connect with optional SSL verification skip."""
        if self.socket:
            return

        # overwrite params if passed in
        if url is not None:
            from surrealdb.connections.url import Url

            self.url = Url(url)
            self.raw_url = f"{self.url.raw_url}/rpc"
            self.host = self.url.hostname
            self.port = self.url.port

        # Create insecure SSL context if using wss://
        ssl_context = None
        if self.raw_url.startswith("wss://"):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        self.socket = await websockets.connect(
            self.raw_url,
            max_size=None,
            subprotocols=[websockets.Subprotocol("cbor")],
            ssl=ssl_context,
        )
        self.loop = asyncio.get_running_loop()
        self.recv_task = asyncio.create_task(self._recv_task())


class ConnectionError(Exception):
    """Database connection error."""

    pass


class QueryError(Exception):
    """Database query error."""

    pass


@dataclass
class ConnectionStats:
    """Connection pool statistics."""

    total_connections: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    total_queries: int = 0
    failed_queries: int = 0
    last_connected: Optional[datetime] = None
    last_error: Optional[str] = None


class Connection:
    """A single SurrealDB connection wrapper.

    Handles connection lifecycle, authentication, and namespace/database selection.
    """

    def __init__(
        self,
        config: SurrealConfig,
        database: str,
    ):
        """Initialize connection.

        Args:
            config: SurrealDB configuration
            database: Database name to use
        """
        self.config = config
        self.database = database
        self._client: Optional[Union[AsyncSurreal, InsecureAsyncWsSurrealConnection]] = None
        self._connected = False
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self._connected and self._client is not None

    def _get_http_url(self) -> str:
        """Convert WebSocket URL to HTTP URL for token auth."""
        url = self.config.url
        if url.startswith("wss://"):
            return url.replace("wss://", "https://")
        elif url.startswith("ws://"):
            return url.replace("ws://", "http://")
        return url

    def _get_auth_token(self) -> str:
        """Get authentication token via HTTP signin."""
        http_url = self._get_http_url()
        signin_url = f"{http_url}/signin"

        try:
            resp = requests.post(
                signin_url,
                json={"user": self.config.user, "pass": self.config.password},
                headers={"Accept": "application/json"},
                timeout=self.config.connect_timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 200:
                raise ConnectionError(f"HTTP signin failed: {data}")

            token = data.get("token")
            if not token:
                raise ConnectionError("No token in signin response")

            return token
        except requests.RequestException as e:
            raise ConnectionError(f"HTTP signin request failed: {e}")

    async def connect(self) -> None:
        """Establish connection to SurrealDB.

        Uses direct WebSocket signin for local development (ws://)
        and HTTP token auth for remote/production (wss://).
        """
        async with self._lock:
            if self._connected:
                return

            try:
                # Step 1: Connect WebSocket
                if self.config.skip_ssl_verify and self.config.url.startswith("wss://"):
                    self._client = InsecureAsyncWsSurrealConnection(self.config.url)
                    logger.warning("SSL verification disabled - not recommended for production")
                else:
                    self._client = AsyncSurreal(self.config.url)

                await asyncio.wait_for(
                    self._client.connect(),
                    timeout=self.config.connect_timeout,
                )

                # Step 2: Authenticate
                if self.config.url.startswith("wss://"):
                    # Remote/production: Use HTTP token auth (works through Traefik)
                    token = self._get_auth_token()
                    logger.debug("Got auth token via HTTP signin")
                    await self._client.authenticate(token)
                else:
                    # Local development: Use direct WebSocket signin
                    # SurrealDB v2 uses username/password format
                    await self._client.signin(
                        {
                            "username": self.config.user,
                            "password": self.config.password,
                        }
                    )
                    logger.debug("Signed in via WebSocket")

                # Step 3: Select namespace/database
                await self._client.use(self.config.namespace, self.database)

                self._connected = True
                logger.debug(f"Connected to SurrealDB: {self.config.namespace}/{self.database}")

            except asyncio.TimeoutError:
                raise ConnectionError(f"Connection timeout after {self.config.connect_timeout}s")
            except ConnectionError:
                raise
            except Exception as e:
                raise ConnectionError(f"Failed to connect: {e}")

    async def disconnect(self) -> None:
        """Close connection."""
        async with self._lock:
            if self._client:
                try:
                    await self._client.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")
                finally:
                    self._client = None
                    self._connected = False

    async def query(
        self,
        sql: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Execute a SurrealQL query.

        Args:
            sql: SurrealQL query string
            params: Query parameters

        Returns:
            List of result records
        """
        if not self.is_connected:
            await self.connect()

        try:
            result = await asyncio.wait_for(
                self._client.query(sql, params or {}),
                timeout=self.config.query_timeout,
            )

            # SurrealDB returns list of results for each statement
            if isinstance(result, list):
                # Flatten results from multiple statements
                records = []
                for stmt_result in result:
                    if isinstance(stmt_result, dict):
                        if "result" in stmt_result:
                            # Standard format: {"result": [...], "status": "OK"}
                            records.extend(stmt_result["result"] or [])
                        elif "id" in stmt_result:
                            # Direct record format (SurrealDB record with id field)
                            records.append(stmt_result)
                        else:
                            logger.debug(
                                f"Skipping unknown query result format: {list(stmt_result.keys())}"
                            )
                    elif isinstance(stmt_result, list):
                        records.extend(stmt_result)
                return records
            return result or []

        except asyncio.TimeoutError:
            raise QueryError(f"Query timeout after {self.config.query_timeout}s")
        except Exception as e:
            raise QueryError(f"Query failed: {e}")

    async def create(
        self,
        table: str,
        data: dict[str, Any],
        record_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a record.

        Args:
            table: Table name
            data: Record data
            record_id: Optional specific record ID

        Returns:
            Created record
        """
        if not self.is_connected:
            await self.connect()

        try:
            thing = f"{table}:{record_id}" if record_id else table
            result = await self._client.create(thing, data)

            if isinstance(result, list):
                return result[0] if result else {}
            return result or {}

        except Exception as e:
            raise QueryError(f"Create failed: {e}")

    async def select(
        self,
        thing: str,
    ) -> list[dict[str, Any]]:
        """Select records.

        Args:
            thing: Table name or specific record (table:id)

        Returns:
            List of records
        """
        if not self.is_connected:
            await self.connect()

        try:
            result = await self._client.select(thing)

            if isinstance(result, list):
                return result
            elif result:
                return [result]
            return []

        except Exception as e:
            raise QueryError(f"Select failed: {e}")

    async def update(
        self,
        thing: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a record.

        Args:
            thing: Record identifier (table:id)
            data: Fields to update

        Returns:
            Updated record
        """
        if not self.is_connected:
            await self.connect()

        try:
            result = await self._client.update(thing, data)

            if isinstance(result, list):
                return result[0] if result else {}
            return result or {}

        except Exception as e:
            raise QueryError(f"Update failed: {e}")

    async def delete(
        self,
        thing: str,
    ) -> bool:
        """Delete a record.

        Args:
            thing: Record identifier (table:id)

        Returns:
            True if deleted
        """
        if not self.is_connected:
            await self.connect()

        try:
            await self._client.delete(thing)
            return True
        except Exception as e:
            raise QueryError(f"Delete failed: {e}")

    async def live(
        self,
        table: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> str:
        """Subscribe to live updates.

        Args:
            table: Table to watch
            callback: Function to call on updates

        Returns:
            Live query UUID for unsubscribing
        """
        if not self.is_connected:
            await self.connect()

        try:
            live_id = await self._client.live(table, callback)
            logger.debug(f"Live query started on {table}: {live_id}")
            return live_id
        except Exception as e:
            raise QueryError(f"Live query failed: {e}")

    async def kill(self, live_id: str) -> None:
        """Stop a live query subscription.

        Args:
            live_id: Live query UUID to stop
        """
        if self._client:
            try:
                await self._client.kill(live_id)
                logger.debug(f"Live query stopped: {live_id}")
            except Exception as e:
                logger.warning(f"Error stopping live query: {e}")


class ConnectionPool:
    """Connection pool for SurrealDB.

    Manages a pool of connections with automatic reconnection
    and health checking.
    """

    def __init__(
        self,
        config: Optional[SurrealConfig] = None,
        database: Optional[str] = None,
    ):
        """Initialize connection pool.

        Args:
            config: SurrealDB configuration
            database: Database name (overrides config default)
        """
        self.config = config or get_config()
        self.database = database or self.config.default_database

        self._connections: list[Connection] = []
        self._available: asyncio.Queue[Connection] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._initialized = False
        self._stats = ConnectionStats()

    @property
    def stats(self) -> ConnectionStats:
        """Get pool statistics."""
        return self._stats

    async def initialize(self) -> None:
        """Initialize the connection pool.

        Creates database if it doesn't exist (per-project isolation).
        """
        async with self._lock:
            if self._initialized:
                return

            # Use standalone function for consistent database name resolution
            db_name = get_project_database(self.database)

            for i in range(self.config.pool_size):
                conn = Connection(self.config, db_name)
                try:
                    await conn.connect()
                    self._connections.append(conn)
                    await self._available.put(conn)
                    self._stats.total_connections += 1
                    self._stats.last_connected = datetime.now()
                except ConnectionError as e:
                    self._stats.failed_connections += 1
                    self._stats.last_error = str(e)
                    logger.warning(f"Failed to create connection {i+1}: {e}")

            if not self._connections:
                raise ConnectionError("Failed to create any connections")

            self._initialized = True
            logger.info(
                f"Connection pool initialized: {len(self._connections)} connections to db={db_name}"
            )

    async def close(self) -> None:
        """Close all connections in the pool."""
        async with self._lock:
            for conn in self._connections:
                await conn.disconnect()

            self._connections.clear()
            self._available = asyncio.Queue()
            self._initialized = False

            logger.info("Connection pool closed")

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[Connection, None]:
        """Acquire a connection from the pool.

        Usage:
            async with pool.acquire() as conn:
                result = await conn.query("SELECT * FROM users")

        Yields:
            Connection instance
        """
        if not self._initialized:
            await self.initialize()

        conn = await self._available.get()
        self._stats.active_connections += 1

        try:
            # Ensure connection is still valid
            if not conn.is_connected:
                await conn.connect()
            yield conn
        finally:
            self._stats.active_connections -= 1
            await self._available.put(conn)

    async def execute(
        self,
        sql: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Execute a query using a pooled connection.

        Args:
            sql: SurrealQL query
            params: Query parameters

        Returns:
            Query results
        """
        async with self.acquire() as conn:
            self._stats.total_queries += 1
            try:
                return await conn.query(sql, params)
            except QueryError:
                self._stats.failed_queries += 1
                raise


# Global connection pools per database
_pools: dict[str, ConnectionPool] = {}
_pools_lock = asyncio.Lock()


async def get_pool(
    project_name: Optional[str] = None,
    config: Optional[SurrealConfig] = None,
) -> ConnectionPool:
    """Get or create a connection pool for a project.

    Each project gets its own database for complete isolation.

    Args:
        project_name: Project name (determines database)
        config: Optional configuration override

    Returns:
        ConnectionPool for the project's database
    """
    cfg = config or get_config()
    # Use standalone function for consistent database naming
    db_name = get_project_database(project_name)

    async with _pools_lock:
        if db_name not in _pools:
            pool = ConnectionPool(cfg, db_name)
            await pool.initialize()
            _pools[db_name] = pool

        return _pools[db_name]


async def close_all_pools() -> None:
    """Close all connection pools."""
    async with _pools_lock:
        for pool in _pools.values():
            await pool.close()
        _pools.clear()


@asynccontextmanager
async def get_connection(
    project_name: Optional[str] = None,
) -> AsyncGenerator[Connection, None]:
    """Context manager for getting a database connection.

    Usage:
        async with get_connection("my-project") as conn:
            await conn.create("tasks", {"title": "Test"})

    Args:
        project_name: Project name

    Yields:
        Database connection
    """
    pool = await get_pool(project_name)
    async with pool.acquire() as conn:
        yield conn
