"""
Custom SQLAlchemy dialect for SQLCipher with async support.

This module provides proper SQLCipher integration with SQLAlchemy
by creating a custom dialect that uses pysqlcipher3 under the hood.
"""

import asyncio
import logging
import threading
import queue
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection
from sqlalchemy.dialects.sqlite.base import SQLiteDialect
from sqlalchemy.engine.interfaces import AdaptedConnection
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import AdaptedConnection

try:
    import pysqlcipher3.dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    sqlcipher = None
    SQLCIPHER_AVAILABLE = False

logger = logging.getLogger(__name__)


class AsyncAdapt_sqlcipher_connection(AsyncAdapt_aiosqlite_connection):
    """
    Async adapter for SQLCipher connections.
    
    This class adapts the SQLCipher connection to work with SQLAlchemy's
    async interface by wrapping synchronous SQLCipher operations.
    """
    
    def __init__(self, dbapi_connection):
        # Don't call super().__init__ as we need custom behavior
        self._connection = dbapi_connection
        self.driver_connection = dbapi_connection


class AsyncAdapt_sqlcipher_cursor:
    """
    Async adapter for SQLCipher cursors.
    """
    
    def __init__(self, cursor):
        self._cursor = cursor
    
    def __getattr__(self, name):
        return getattr(self._cursor, name)


class SQLCipherDialect(SQLiteDialect):
    """
    Custom SQLAlchemy dialect for SQLCipher encryption.
    
    This dialect extends the standard SQLite dialect to support
    SQLCipher encrypted databases with proper async operation.
    """
    
    driver = "sqlcipher"
    name = "sqlite"
    
    @classmethod
    def import_dbapi(cls):
        """Import the SQLCipher DBAPI module."""
        if not SQLCIPHER_AVAILABLE:
            raise ImportError("pysqlcipher3 is required for SQLCipher support")
        return sqlcipher
    
    def create_connect_args(self, url):
        """
        Create connection arguments for SQLCipher.
        
        Extracts the encryption key from the URL and sets up
        proper SQLCipher connection parameters.
        """
        # Get base connection args from parent
        super_result = super().create_connect_args(url)
        cargs, cparams = super_result
        
        # Extract encryption key from URL query parameters
        parsed_url = urlparse(str(url))
        query_params = parse_qs(parsed_url.query)
        
        if 'key' in query_params:
            encryption_key = query_params['key'][0]
            
            # Add SQLCipher-specific connection setup
            def creator():
                # Create connection to database file
                db_path = cargs[0] if cargs else url.database
                conn = sqlcipher.connect(db_path, **cparams)
                
                # Set encryption key
                conn.execute(f"PRAGMA key = '{encryption_key}'")
                
                # Verify encryption is working by testing access
                try:
                    conn.execute("SELECT count(*) FROM sqlite_master")
                except sqlcipher.DatabaseError as e:
                    if "file is not a database" in str(e).lower():
                        raise EncryptionError(
                            "Database file exists but cannot be decrypted. "
                            "Wrong encryption key or corrupted database."
                        ) from e
                    raise
                
                # Configure SQLite pragmas for performance and WAL mode
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=10000")
                conn.execute("PRAGMA temp_store=MEMORY")
                
                logger.debug("SQLCipher connection established with encryption")
                return conn
            
            # Return custom creator function
            return ([], {'creator': creator})
        else:
            logger.warning("No encryption key found in SQLCipher URL")
            return super_result
    
    def get_pool_class(self, url):
        """Force use of StaticPool for SQLite databases."""
        return StaticPool
    
    def is_disconnect(self, e, connection, cursor):
        """Check if error indicates a database disconnection."""
        if isinstance(e, sqlcipher.Error):
            return "database is locked" in str(e).lower()
        return super().is_disconnect(e, connection, cursor)


# Define EncryptionError locally to avoid circular import
class EncryptionError(Exception):
    """Exception for encryption-related database errors."""
    pass


# Register the dialect with SQLAlchemy
from sqlalchemy.dialects import registry
registry.register("sqlite.async_sqlcipher", "walnut.database.sqlcipher_dialect", "SQLCipherDialect")


def test_sqlcipher_encryption(db_path: str, key: str) -> Dict[str, Any]:
    """
    Test SQLCipher encryption by creating a test database and verifying
    it cannot be opened without the correct key.
    
    Args:
        db_path: Path to test database file
        key: Encryption key to test
        
    Returns:
        Dict containing test results
        
    Raises:
        EncryptionError: If encryption test fails
    """
    import os
    import tempfile
    from pathlib import Path
    
    if not SQLCIPHER_AVAILABLE:
        raise EncryptionError("pysqlcipher3 not available for encryption testing")
    
    test_db = Path(db_path).parent / f"encryption_test_{os.getpid()}.db"
    
    try:
        # Create encrypted test database
        conn = sqlcipher.connect(str(test_db))
        conn.execute(f"PRAGMA key = '{key}'")
        
        # Create a test table and insert data
        conn.execute("CREATE TABLE test_encryption (id INTEGER, data TEXT)")
        conn.execute("INSERT INTO test_encryption (id, data) VALUES (1, 'encrypted_data')")
        conn.commit()
        conn.close()
        
        # Verify file exists and has content
        if not test_db.exists() or test_db.stat().st_size == 0:
            raise EncryptionError("Encrypted database file was not created")
        
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
            # This is expected - wrong key should fail
            if "file is not a database" not in str(e).lower():
                raise EncryptionError(f"Wrong key gave unexpected error: {e}")
        
        # Test 3: Verify we cannot open as regular SQLite
        try:
            import sqlite3
            conn = sqlite3.connect(str(test_db))
            conn.execute("SELECT count(*) FROM sqlite_master")
            conn.close()
            raise EncryptionError("Database opened as regular SQLite - encryption not working!")
        except sqlite3.DatabaseError as e:
            # This is expected - encrypted database should not open as regular SQLite
            if "file is not a database" not in str(e).lower():
                raise EncryptionError(f"Regular SQLite gave unexpected error: {e}")
        
        return {
            "encryption_verified": True,
            "database_size": test_db.stat().st_size,
            "tests_passed": [
                "correct_key_access",
                "wrong_key_denied",
                "regular_sqlite_denied"
            ]
        }
        
    finally:
        # Clean up test database
        try:
            if test_db.exists():
                test_db.unlink()
            # Also clean up WAL and SHM files
            for suffix in ['-wal', '-shm']:
                wal_file = Path(str(test_db) + suffix)
                if wal_file.exists():
                    wal_file.unlink()
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup test database: {cleanup_error}")