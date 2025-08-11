"""
Async SQLCipher adapter for walNUT.

This module provides an async-compatible interface to SQLCipher
by running pysqlcipher3 operations in a thread pool executor.
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

try:
    import pysqlcipher3.dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    sqlcipher = None
    SQLCIPHER_AVAILABLE = False

logger = logging.getLogger(__name__)


class AsyncSQLCipherConnection:
    """
    Async wrapper for SQLCipher connections.
    
    This class provides an async interface to SQLCipher by executing
    all database operations in a thread pool executor.
    """
    
    def __init__(self, database_path: str, encryption_key: str, timeout: int = 30):
        """
        Initialize async SQLCipher connection.
        
        Args:
            database_path: Path to the encrypted database file
            encryption_key: Encryption key for the database
            timeout: Connection timeout in seconds
        """
        self.database_path = database_path
        self.encryption_key = encryption_key
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sqlcipher")
        self._connection = None
        self._lock = threading.Lock()
    
    async def connect(self) -> None:
        """Establish connection to the encrypted database."""
        def _connect():
            if not SQLCIPHER_AVAILABLE:
                raise RuntimeError("pysqlcipher3 not available")
            
            conn = sqlcipher.connect(
                self.database_path,
                check_same_thread=False,
                timeout=self.timeout,
            )
            
            # Set encryption key - escape single quotes to prevent SQL injection
            escaped_key = self.encryption_key.replace("'", "''")
            conn.execute(f"PRAGMA key = '{escaped_key}'")
            
            # Configure database settings
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")
            
            return conn
        
        self._connection = await asyncio.get_event_loop().run_in_executor(
            self._executor, _connect
        )
        logger.debug(f"Connected to encrypted database: {self.database_path}")
    
    async def execute(self, sql: str, parameters: Optional[Tuple] = None) -> Any:
        """Execute SQL statement and return cursor."""
        if not self._connection:
            await self.connect()
        
        def _execute():
            with self._lock:
                cursor = self._connection.cursor()
                if parameters:
                    cursor.execute(sql, parameters)
                else:
                    cursor.execute(sql)
                return cursor
        
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, _execute
        )
    
    async def executemany(self, sql: str, parameters: List[Tuple]) -> Any:
        """Execute SQL statement with multiple parameter sets."""
        if not self._connection:
            await self.connect()
        
        def _executemany():
            with self._lock:
                cursor = self._connection.cursor()
                cursor.executemany(sql, parameters)
                return cursor
        
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, _executemany
        )
    
    async def fetchone(self, cursor) -> Optional[Tuple]:
        """Fetch one row from cursor."""
        def _fetchone():
            return cursor.fetchone()
        
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, _fetchone
        )
    
    async def fetchall(self, cursor) -> List[Tuple]:
        """Fetch all rows from cursor."""
        def _fetchall():
            return cursor.fetchall()
        
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, _fetchall
        )
    
    async def commit(self) -> None:
        """Commit current transaction."""
        if not self._connection:
            return
        
        def _commit():
            with self._lock:
                self._connection.commit()
        
        await asyncio.get_event_loop().run_in_executor(
            self._executor, _commit
        )
    
    async def rollback(self) -> None:
        """Rollback current transaction."""
        if not self._connection:
            return
        
        def _rollback():
            with self._lock:
                self._connection.rollback()
        
        await asyncio.get_event_loop().run_in_executor(
            self._executor, _rollback
        )
    
    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            def _close():
                with self._lock:
                    self._connection.close()
            
            await asyncio.get_event_loop().run_in_executor(
                self._executor, _close
            )
            self._connection = None
        
        # Shutdown executor
        self._executor.shutdown(wait=True)
        logger.debug("Closed encrypted database connection")

    async def run_sync(self, fn, *args, **kwargs):
        """
        Run a synchronous function in the thread pool.
        The function will be passed a synchronous SQLAlchemy connection.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from sqlalchemy.dialects.sqlite import pysqlite
        import types

        def _run():
            # We need a sync SQLAlchemy engine to get a sync connection

            # Store original on_connect for restoration later
            original_on_connect = pysqlite.dialect.on_connect

            # Define custom on_connect that skips problematic functions
            def sqlcipher_on_connect(self):
                """Custom on_connect that skips regexp function registration."""
                def connect(conn):
                    # Only enable foreign keys, skip other function registrations
                    conn.execute("PRAGMA foreign_keys=ON")
                return connect

            # Temporarily patch the dialect
            pysqlite.dialect.on_connect = sqlcipher_on_connect

            try:
                engine = create_engine(
                    "sqlite://",  # Dummy URL, we use the creator
                    creator=lambda: self._connection,
                    poolclass=StaticPool,
                )
                with engine.connect() as conn:
                    return fn(conn, *args, **kwargs)
            finally:
                # Restore original on_connect to avoid affecting other engines
                pysqlite.dialect.on_connect = original_on_connect

        return await asyncio.get_event_loop().run_in_executor(
            self._executor, _run
        )
    
    @asynccontextmanager
    async def transaction(self):
        """Context manager for database transactions."""
        try:
            yield self
            await self.commit()
        except Exception:
            await self.rollback()
            raise
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test the database connection and return diagnostics."""
        if not self._connection:
            await self.connect()
        
        try:
            # Test basic connectivity
            cursor = await self.execute("SELECT 1 as test")
            result = await self.fetchone(cursor)
            test_value = result[0] if result else None
            
            # Get SQLite version
            cursor = await self.execute("SELECT sqlite_version()")
            result = await self.fetchone(cursor)
            sqlite_version = result[0] if result else None
            
            # Test SQLCipher
            try:
                cursor = await self.execute("PRAGMA cipher_version")
                result = await self.fetchone(cursor)
                cipher_version = result[0] if result else None
            except Exception:
                cipher_version = None
            
            # Get journal mode
            cursor = await self.execute("PRAGMA journal_mode")
            result = await self.fetchone(cursor)
            journal_mode = result[0] if result else None
            
            return {
                "connection_test": test_value == 1,
                "sqlite_version": sqlite_version,
                "cipher_version": cipher_version,
                "journal_mode": journal_mode,
                "encryption_enabled": True,
                "wal_mode_enabled": journal_mode == "wal",
            }
            
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return {
                "connection_test": False,
                "error": str(e),
            }


def create_encrypted_database(db_path: str, encryption_key: str) -> None:
    """
    Create a new encrypted database file.
    
    Args:
        db_path: Path where to create the database
        encryption_key: Encryption key to use
    """
    if not SQLCIPHER_AVAILABLE:
        raise RuntimeError("pysqlcipher3 not available")
    
    conn = sqlcipher.connect(db_path)
    escaped_key = encryption_key.replace("'", "''")
    conn.execute(f"PRAGMA key = '{escaped_key}'")
    
    # Configure database settings
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    
    # Create a test table to ensure encryption is working
    conn.execute("CREATE TABLE encryption_test (id INTEGER PRIMARY KEY, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO encryption_test DEFAULT VALUES")
    conn.commit()
    conn.close()
    
    logger.info(f"Created encrypted database: {db_path}")


async def test_encrypted_database(db_path: str, encryption_key: str) -> Dict[str, Any]:
    """
    Test that a database is properly encrypted.
    
    Args:
        db_path: Path to the database file
        encryption_key: Encryption key to test
        
    Returns:
        Dict with test results
    """
    # Test 1: Verify we can read with correct key
    conn = AsyncSQLCipherConnection(db_path, encryption_key)
    try:
        diagnostics = await conn.test_connection()
        if not diagnostics["connection_test"]:
            return {"encryption_verified": False, "error": "Cannot connect with provided key"}
        
        # Test 2: Verify file is actually encrypted (binary check)
        with open(db_path, 'rb') as f:
            file_content = f.read(16)  # Read first 16 bytes
        
        # SQLite files normally start with "SQLite format 3"
        sqlite_magic = b"SQLite format 3"
        is_encrypted = not file_content.startswith(sqlite_magic)
        
        # Test 3: Try to open as regular SQLite (should fail)
        regular_sqlite_fails = False
        try:
            import sqlite3
            test_conn = sqlite3.connect(db_path)
            test_conn.execute("SELECT COUNT(*) FROM sqlite_master")
            test_conn.close()
        except sqlite3.DatabaseError:
            regular_sqlite_fails = True
        
        return {
            "encryption_verified": is_encrypted and regular_sqlite_fails,
            "file_encrypted": is_encrypted,
            "regular_sqlite_blocked": regular_sqlite_fails,
            "connection_works": diagnostics["connection_test"],
            "wal_mode": diagnostics.get("wal_mode_enabled", False),
            "diagnostics": diagnostics,
        }
        
    finally:
        await conn.close()