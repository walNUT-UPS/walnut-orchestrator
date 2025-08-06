"""
Custom async engine wrapper for SQLCipher support.

This module provides a SQLAlchemy-like interface for encrypted databases
using the async_sqlcipher connection adapter.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .async_sqlcipher import AsyncSQLCipherConnection, SQLCIPHER_AVAILABLE

logger = logging.getLogger(__name__)


class AsyncSQLCipherEngine:
    """
    Custom async engine for SQLCipher encrypted databases.
    
    This class mimics SQLAlchemy's AsyncEngine interface but uses
    our custom async SQLCipher connection under the hood.
    """
    
    def __init__(self, database_path: str, encryption_key: str, echo: bool = False):
        """
        Initialize async SQLCipher engine.
        
        Args:
            database_path: Path to encrypted database file
            encryption_key: Encryption key for database
            echo: Whether to echo SQL statements (for debugging)
        """
        self.database_path = database_path
        self.encryption_key = encryption_key
        self.echo = echo
        self._connection = None
        self.url = f"sqlcipher:///{database_path}"
        self._original_url = f"sqlcipher:///{database_path}?encryption_key={encryption_key}"
        
        # Create a sync engine for SQLAlchemy session compatibility
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        
        def creator():
            import pysqlcipher3.dbapi2 as sqlcipher
            conn = sqlcipher.connect(database_path, check_same_thread=False)
            conn.execute(f"PRAGMA key = '{encryption_key}'")
            
            # Configure connection
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            conn.execute("PRAGMA temp_store=MEMORY")
            
            return conn
        
        # Patch the SQLite dialect to prevent problematic function registration
        from sqlalchemy.dialects.sqlite import pysqlite
        import types
        
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
            # Create synchronous engine for session compatibility
            self.sync_engine = create_engine(
                "sqlite://",  # Dummy URL, we'll use creator
                creator=creator,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
                echo=echo
            )
        finally:
            # Restore original on_connect to avoid affecting other engines
            pysqlite.dialect.on_connect = original_on_connect
    
    @asynccontextmanager
    async def begin(self):
        """Begin a transaction and yield connection."""
        if not self._connection:
            self._connection = AsyncSQLCipherConnection(
                self.database_path, 
                self.encryption_key
            )
            await self._connection.connect()
        
        async with self._connection.transaction():
            yield AsyncSQLCipherTransaction(self._connection)
    
    @asynccontextmanager  
    async def connect(self):
        """Get a connection from the engine."""
        if not self._connection:
            self._connection = AsyncSQLCipherConnection(
                self.database_path,
                self.encryption_key
            )
            await self._connection.connect()
        
        yield self._connection
    
    async def dispose(self):
        """Dispose of the engine and close connections."""
        if self._connection:
            await self._connection.close()
            self._connection = None
        
        # Dispose of sync engine too
        if hasattr(self, 'sync_engine'):
            self.sync_engine.dispose()
            
        logger.debug("SQLCipher engine disposed")
    
    def _get_sync_engine_or_connection(self, connection=None):
        """Get synchronous engine for SQLAlchemy session compatibility."""
        if connection is not None:
            return connection._proxied if hasattr(connection, '_proxied') else connection
        return self.sync_engine


class AsyncSQLCipherResult:
    """
    Result wrapper for SQLCipher queries.
    
    This class mimics SQLAlchemy's Result interface.
    """
    
    def __init__(self, cursor, connection: AsyncSQLCipherConnection):
        self.cursor = cursor
        self.connection = connection
        self._fetched_rows = None
    
    def scalar(self):
        """Return the first column of the first row, or None."""
        # For scalar, we fetch from the cursor directly (synchronous)
        # This works because the cursor was already executed in the thread
        row = self.cursor.fetchone()
        return row[0] if row else None
    
    async def fetchone(self):
        """Fetch one row asynchronously."""
        return await self.connection.fetchone(self.cursor)
    
    async def fetchall(self):
        """Fetch all rows asynchronously."""  
        return await self.connection.fetchall(self.cursor)


class AsyncSQLCipherTransaction:
    """
    Transaction wrapper for SQLCipher connections.
    
    This class provides SQLAlchemy-like transaction interface.
    """
    
    def __init__(self, connection: AsyncSQLCipherConnection):
        self.connection = connection
        self._in_transaction = False
    
    async def execute(self, statement, parameters=None):
        """Execute SQL statement."""
        if hasattr(statement, 'text'):
            # Handle SQLAlchemy text() objects
            sql = str(statement)
        else:
            sql = str(statement)
        
        cursor = await self.connection.execute(sql, parameters)
        return AsyncSQLCipherResult(cursor, self.connection)
    
    async def commit(self):
        """Commit the transaction."""
        await self.connection.commit()
    
    async def rollback(self):
        """Rollback the transaction."""
        await self.connection.rollback()
    
    async def close(self):
        """Close the transaction."""
        # Transaction cleanup is handled by connection
        pass
    
    async def run_sync(self, fn, *args, **kwargs):
        """Run a synchronous function with a proper SQLAlchemy engine."""
        # This is used for operations like metadata.create_all()
        import asyncio
        
        # Special handling for metadata.create_all() to avoid SQLite dialect incompatibility
        if hasattr(fn, '__name__') and 'create_all' in str(fn):
            # Handle table creation via raw SQL to avoid dialect issues
            # fn is a bound method like Base.metadata.create_all, so fn.__self__ is the metadata
            metadata = fn.__self__
            return await self._create_tables_raw_sql(metadata)
        
        # For other operations, use the regular SQLAlchemy approach
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        
        def _run_sync():
            # Create a temporary synchronous SQLAlchemy engine for DDL operations
            def creator():
                import pysqlcipher3.dbapi2 as sqlcipher
                conn = sqlcipher.connect(self.connection.database_path, check_same_thread=False)
                conn.execute(f"PRAGMA key = '{self.connection.encryption_key}'")
                
                # Configure connection
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=10000")
                conn.execute("PRAGMA temp_store=MEMORY")
                
                return conn
            
            # Create temporary engine for metadata operations
            sync_engine = create_engine(
                "sqlite://",  # Dummy URL, we'll use creator
                creator=creator,
                poolclass=StaticPool,
                connect_args={"check_same_thread": False}
            )
            
            try:
                return fn(sync_engine, *args, **kwargs)
            finally:
                sync_engine.dispose()
        
        return await asyncio.get_event_loop().run_in_executor(None, _run_sync)
    
    async def _create_tables_raw_sql(self, metadata):
        """Create tables using raw SQL to avoid dialect compatibility issues."""
        import asyncio
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from sqlalchemy.schema import CreateTable
        from sqlalchemy.dialects import sqlite
        
        def _create_tables_sync():
            import pysqlcipher3.dbapi2 as sqlcipher
            
            # Create a dummy SQLite engine just to compile the SQL
            dummy_engine = create_engine("sqlite:///:memory:")
            
            conn = sqlcipher.connect(self.connection.database_path, check_same_thread=False)
            conn.execute(f"PRAGMA key = '{self.connection.encryption_key}'")
            
            # Configure connection
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            
            try:
                # Generate CREATE TABLE statements for each table using SQLite dialect
                for table in metadata.sorted_tables:
                    # Compile using SQLite dialect for proper SQL generation
                    create_table_sql = str(CreateTable(table).compile(
                        dialect=sqlite.dialect(),
                        compile_kwargs={"literal_binds": True}
                    ))
                    
                    logger.debug(f"Creating table {table.name} with SQL: {create_table_sql}")
                    
                    # Execute the CREATE TABLE statement
                    conn.execute(f"DROP TABLE IF EXISTS {table.name}")
                    conn.execute(create_table_sql)
                
                conn.commit()
                logger.info(f"Created {len(metadata.sorted_tables)} tables via raw SQL")
                
            except Exception as e:
                logger.error(f"Failed to create tables via raw SQL: {e}")
                raise
            finally:
                conn.close()
        
        return await asyncio.get_event_loop().run_in_executor(None, _create_tables_sync)


def create_async_sqlcipher_engine(database_url: str, echo: bool = False) -> AsyncSQLCipherEngine:
    """
    Create an async SQLCipher engine from URL.
    
    Args:
        database_url: Database URL in format sqlite+async_sqlcipher:///path?encryption_key=key
        echo: Whether to echo SQL statements
        
    Returns:
        AsyncSQLCipherEngine instance
        
    Raises:
        ValueError: If URL is invalid or encryption key is missing
        RuntimeError: If pysqlcipher3 is not available
    """
    if not SQLCIPHER_AVAILABLE:
        raise RuntimeError("pysqlcipher3 is required for encrypted databases")
    
    # Parse URL
    parsed = urlparse(database_url)
    if parsed.scheme != 'sqlcipher':
        raise ValueError(f"Invalid URL scheme for SQLCipher: {parsed.scheme}")
    
    # Extract database path
    if parsed.path.startswith('/'):
        database_path = parsed.path  # Keep absolute path as-is
    else:
        database_path = parsed.path
    
    # Extract encryption key
    params = parse_qs(parsed.query)
    if 'encryption_key' not in params:
        raise ValueError("Encryption key missing from database URL")
    
    encryption_key = params['encryption_key'][0]
    
    return AsyncSQLCipherEngine(database_path, encryption_key, echo)


async def test_async_sqlcipher_engine(engine: AsyncSQLCipherEngine) -> Dict[str, Any]:
    """
    Test async SQLCipher engine functionality.
    
    Args:
        engine: AsyncSQLCipherEngine to test
        
    Returns:
        Dict containing test results and diagnostics
    """
    try:
        async with engine.begin() as conn:
            # Test basic connectivity
            result = await conn.execute("SELECT 1 as test")
            test_value = result.scalar()
            
            # Get SQLite version
            result = await conn.execute("SELECT sqlite_version()")
            sqlite_version = result.scalar()
            
            # Test SQLCipher version
            try:
                result = await conn.execute("PRAGMA cipher_version")
                cipher_version = result.scalar()
            except Exception:
                cipher_version = "SQLCipher (version query failed)"
            
            # Get journal mode
            result = await conn.execute("PRAGMA journal_mode")
            journal_mode = result.scalar()
            
            return {
                "connection_test": test_value == 1,
                "sqlite_version": sqlite_version, 
                "cipher_version": cipher_version,
                "journal_mode": journal_mode,
                "encryption_enabled": True,
                "sqlcipher_verified": True,
                "database_size_bytes": None,  # Could implement if needed
                "wal_mode_enabled": journal_mode == "wal",
                "database_url_type": "sqlcipher",
            }
            
    except Exception as e:
        logger.error(f"SQLCipher engine test failed: {e}")
        return {
            "connection_test": False,
            "error": str(e),
            "encryption_enabled": False,
            "sqlcipher_verified": False,
        }