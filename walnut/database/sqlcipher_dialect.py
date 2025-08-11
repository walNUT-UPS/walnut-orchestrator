"""
Custom SQLAlchemy dialect for SQLCipher with async support.
This module provides proper SQLCipher integration with SQLAlchemy
by creating a custom dialect that uses pysqlcipher3 under the hood,
with all blocking calls wrapped in asyncio.to_thread.
"""

import asyncio
import logging
from typing import Any, Dict
from urllib.parse import parse_qs, unquote

from sqlalchemy.dialects.sqlite.base import SQLiteDialect
from sqlalchemy.engine.interfaces import AdaptedConnection, DBAPIConnection
from sqlalchemy.pool import StaticPool

try:
    import pysqlcipher3.dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    sqlcipher = None
    SQLCIPHER_AVAILABLE = False

logger = logging.getLogger(__name__)

class AsyncAdapt_pysqlcipher_cursor:
    """Async adapter for pysqlcipher3 cursors."""

    __slots__ = ("_cursor", "_connection")

    def __init__(self, cursor, connection):
        self._cursor = cursor
        self._connection = connection

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def arraysize(self):
        return self._cursor.arraysize

    @arraysize.setter
    def arraysize(self, value):
        self._cursor.arraysize = value

    async def execute(self, operation, parameters=None):
        return await self._connection._run(
            self._cursor.execute, operation, parameters or ()
        )

    async def executemany(self, operation, seq_of_parameters):
        return await self._connection._run(
            self._cursor.executemany, operation, seq_of_parameters
        )

    async def fetchone(self):
        return await self._connection._run(self._cursor.fetchone)

    async def fetchmany(self, size=None):
        if size is None:
            size = self.arraysize
        return await self._connection._run(self._cursor.fetchmany, size)

    async def fetchall(self):
        return await self._connection._run(self._cursor.fetchall)

    async def close(self):
        await self._connection._run(self._cursor.close)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class AsyncAdapt_pysqlcipher_connection(AdaptedConnection):
    """Async adapter for pysqlcipher3 connections."""

    __slots__ = ("_connection",)

    def __init__(self, connection: DBAPIConnection):
        self._connection = connection

    @classmethod
    async def connect(cls, **kwargs):
        return await asyncio.to_thread(sqlcipher.connect, **kwargs)

    async def cursor(self, *args, **kwargs):
        return AsyncAdapt_pysqlcipher_cursor(
            await self._run(self._connection.cursor, *args, **kwargs), self
        )

    async def commit(self):
        await self._run(self._connection.commit)

    async def rollback(self):
        await self._run(self._connection.rollback)

    async def close(self):
        await self._run(self._connection.close)

    async def _run(self, fn, *args, **kwargs):
        """Run a sync function in a thread."""
        return await asyncio.to_thread(fn, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._connection, name)


class SQLCipherDialect_pysqlcipher(SQLiteDialect):
    """
    Custom SQLAlchemy dialect for SQLCipher encryption using pysqlcipher3.
    This dialect provides an async interface for pysqlcipher3.
    """
    driver = "sqlcipher"
    name = "sqlite"
    supports_statement_cache = True
    dbapi_version = sqlcipher.version_info
    sqlite_version_info = sqlcipher.sqlite_version_info

    # this indicates that the pysqlcipher DBAPI is not thread-safe
    is_async = True

    @classmethod
    def import_dbapi(cls):
        """Import the pysqlcipher3 DBAPI module."""
        if not SQLCIPHER_AVAILABLE:
            raise ImportError("pysqlcipher3 is required for SQLCipher support")
        return sqlcipher

    def get_pool_class(self, url):
        """Force use of StaticPool for SQLite databases."""
        return StaticPool

    def create_connect_args(self, url):
        """Create connection arguments for SQLCipher."""
        opts = url.translate_connect_args()
        opts.update(url.query)

        # get the encryption key
        if "key" not in opts:
            raise EncryptionError(
                "Encryption key must be provided in the database URL "
                "as a query parameter, e.g., ?key=my_secret_key"
            )
        key = opts.pop("key")

        # check_same_thread must be False for async operation
        opts["check_same_thread"] = False
        filename = opts.pop("database", ":memory:")

        return ([filename], opts)

    def _init_dbapi_attributes(self):
        self.dbapi = self.import_dbapi()
        self.paramstyle = "qmark"

    def get_async_connection_cls(self):
        return AsyncAdapt_pysqlcipher_connection

    async def do_connect(self, cargs, cparams):
        """Connect to the database."""
        key = cparams.pop("key")
        connection = await AsyncAdapt_pysqlcipher_connection.connect(*cargs, **cparams)

        # Set the encryption key using PRAGMA
        # The key must be passed as a raw string literal to avoid issues with special characters
        # The key itself should be a string of hex digits, e.g. "x'234...'"
        # For simplicity, we will just quote it.
        await connection.execute(f"PRAGMA key = '{key}'")

        # Set WAL mode and other pragmas for performance
        await connection.execute("PRAGMA journal_mode=WAL;")
        await connection.execute("PRAGMA busy_timeout=5000;")
        await connection.execute("PRAGMA foreign_keys=ON;")
        await connection.execute("PRAGMA synchronous=NORMAL;")
        await connection.execute("PRAGMA cache_size=10000;")
        await connection.execute("PRAGMA temp_store=MEMORY;")

        return connection

    def is_disconnect(self, e, connection, cursor):
        """Check if error indicates a database disconnection."""
        if isinstance(e, self.dbapi.OperationalError):
            return "database is locked" in str(e).lower() or \
                   "database is closed" in str(e).lower()
        return super().is_disconnect(e, connection, cursor)


# Define EncryptionError locally to avoid circular import
class EncryptionError(Exception):
    """Exception for encryption-related database errors."""
    pass

# Register the dialect with SQLAlchemy
from sqlalchemy.dialects import registry
registry.register(
    "sqlite.sqlcipher", "walnut.database.sqlcipher_dialect", "SQLCipherDialect_pysqlcipher"
)

def test_sqlcipher_encryption(db_path: str, key: str) -> Dict[str, Any]:
    """
    Test SQLCipher encryption by creating a test database and verifying
    it cannot be opened without the correct key.
    This is a synchronous test function.
    """
    import os
    from pathlib import Path

    if not SQLCIPHER_AVAILABLE:
        raise EncryptionError("pysqlcipher3 not available for encryption testing")

    test_db = Path(db_path).parent / f"encryption_test_{os.getpid()}.db"

    try:
        # Create encrypted test database
        conn = sqlcipher.connect(str(test_db))
        conn.execute(f"PRAGMA key = '{key}'")
        conn.execute("CREATE TABLE test_encryption (id INTEGER, data TEXT)")
        conn.execute("INSERT INTO test_encryption (id, data) VALUES (1, 'encrypted_data')")
        conn.commit()
        conn.close()

        # Test 1: Verify we can open with correct key
        conn = sqlcipher.connect(str(test_db))
        conn.execute(f"PRAGMA key = '{key}'")
        cursor = conn.execute("SELECT data FROM test_encryption WHERE id = 1")
        result = cursor.fetchone()
        if not result or result[0] != 'encrypted_data':
            raise EncryptionError("Could not read data with correct key")
        conn.close()

        # Test 2: Verify we cannot open with wrong key
        try:
            conn = sqlcipher.connect(str(test_db))
            conn.execute("PRAGMA key = 'wrong_key'")
            conn.execute("SELECT count(*) FROM sqlite_master")
            conn.close()
            raise EncryptionError("Database opened with wrong key - encryption not working!")
        except sqlcipher.DatabaseError as e:
            if "file is not a database" not in str(e).lower():
                raise EncryptionError(f"Wrong key gave unexpected error: {e}")

        return {
            "encryption_verified": True,
            "tests_passed": ["correct_key_access", "wrong_key_denied"],
        }
    finally:
        if test_db.exists():
            test_db.unlink()