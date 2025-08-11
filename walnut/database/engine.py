"""
Database engine configuration with SQLCipher encryption and WAL mode.

This module provides the core database engine setup for walNUT, including:
- SQLCipher AES-256 encryption
- WAL (Write-Ahead Logging) mode for concurrent access
- Connection pooling with busy timeout
- Local disk validation
- Master key management from environment/Docker secrets
"""

import asyncio
import logging
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote

import aiosqlite
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

# Import SQLCipher dialect
from .sqlcipher_dialect import test_sqlcipher_encryption

# Import pysqlcipher3 for encrypted database support
try:
    import pysqlcipher3.dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    sqlcipher = None
    SQLCIPHER_AVAILABLE = False


logger = logging.getLogger(__name__)


def _ensure_encrypted_database(db_path: Path, encryption_key: str) -> None:
    """
    Ensure the database file exists and is encrypted with SQLCipher.
    
    Uses the async_sqlcipher module to create and verify encrypted databases.
    
    Args:
        db_path: Path to the database file
        encryption_key: Encryption key to use
        
    Raises:
        EncryptionError: If database exists but can't be opened with key
        DatabaseError: If database creation fails
    """
    try:
        from .async_sqlcipher import create_encrypted_database, test_encrypted_database
        
        if not db_path.exists():
            logger.info(f"Creating new encrypted database at {db_path}")
            create_encrypted_database(str(db_path), encryption_key)
            logger.info("Encrypted database created successfully")
        else:
            logger.debug(f"Verifying existing encrypted database at {db_path}")
            
            # Test that the database can be opened with the key
            # We need to run this async test in a sync context
            import asyncio
            try:
                # Get or create event loop
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in an async context, we can't use run_until_complete
                    # Instead, we'll do a basic sync verification
                    conn = sqlcipher.connect(str(db_path))
                    escaped_key = encryption_key.replace("'", "''")
                    conn.execute(f"PRAGMA key = '{escaped_key}'")
                    conn.execute("SELECT count(*) FROM sqlite_master")
                    conn.close()
                    logger.debug("Existing encrypted database verified (sync)")
                except RuntimeError:
                    # No running loop, we can use run_until_complete
                    result = asyncio.run(test_encrypted_database(str(db_path), encryption_key))
                    if not result.get("encryption_verified", False):
                        raise EncryptionError(
                            f"Database file {db_path} verification failed: {result.get('error', 'Unknown error')}"
                        )
                    logger.debug("Existing encrypted database verified (async)")
                    
            except sqlcipher.DatabaseError as e:
                if "file is not a database" in str(e).lower():
                    raise EncryptionError(
                        f"Database file {db_path} exists but cannot be decrypted with the provided key. "
                        "Wrong encryption key or corrupted database file."
                    ) from e
                raise DatabaseError(f"Failed to verify encrypted database: {e}") from e
                
    except EncryptionError:
        raise
    except Exception as e:
        logger.error(f"Failed to ensure encrypted database: {e}")
        raise DatabaseError(f"Database encryption setup failed: {e}") from e


class DatabaseError(Exception):
    """Base exception for database-related errors."""
    pass


class EncryptionError(DatabaseError):
    """Exception for encryption-related database errors."""
    pass


class ValidationError(DatabaseError):
    """Exception for database validation errors.""" 
    pass


def get_master_key() -> str:
    """
    Retrieve the database master key from environment or Docker secrets.
    
    Returns:
        str: The master key for database encryption
        
    Raises:
        EncryptionError: If no master key is found or key is invalid
    """
    # Try Docker secrets first
    secrets_path = Path("/run/secrets/walnut_db_key")
    if secrets_path.exists():
        try:
            key = secrets_path.read_text().strip()
            if key and len(key) >= 32:  # Minimum 32 chars for AES-256
                logger.info("Master key loaded from Docker secrets")
                return key
        except (OSError, IOError) as e:
            logger.warning(f"Failed to read Docker secret: {e}")
    
    # Fall back to environment variable
    key = os.getenv("WALNUT_DB_KEY")
    if key and len(key) >= 32:
        logger.info("Master key loaded from environment variable")
        return key
    
    # Development fallback (warn about security)
    dev_key = os.getenv("WALNUT_DB_KEY_DEV")
    if dev_key:
        logger.warning(
            "Using development master key - NOT SUITABLE FOR PRODUCTION!"
        )
        return dev_key
    
    raise EncryptionError(
        "No valid master key found. Set WALNUT_DB_KEY environment variable "
        "or mount key as Docker secret at /run/secrets/walnut_db_key. "
        "Key must be at least 32 characters long."
    )


def validate_database_path(db_path: Path) -> None:
    """
    Validate that the database path is on a local filesystem.
    
    This prevents issues with network filesystems that don't support
    SQLite's locking mechanisms properly.
    
    Args:
        db_path: Path to the database file
        
    Raises:
        ValidationError: If path is on a network filesystem or invalid
    """
    try:
        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Test with a temporary file in the same directory
        test_file = db_path.parent / f".walnut_test_{os.getpid()}"
        try:
            # Create test file
            test_file.touch()
            
            # Check if we can get file stats (fails on some network FS)
            stat_info = test_file.stat()
            
            # Check for common network filesystem indicators
            if hasattr(stat_info, 'st_dev'):
                # On Linux, check for NFS/CIFS magic numbers
                if hasattr(os, 'statvfs'):
                    try:
                        vfs = os.statvfs(str(test_file))
                        # Common network FS fstype values that cause issues
                        if hasattr(vfs, 'f_type'):
                            network_fs_types = {
                                0x6969,     # NFS
                                0xFF534D42, # CIFS/SMB
                                0x73757246, # FUSE (often network)
                            }
                            if vfs.f_type in network_fs_types:
                                raise ValidationError(
                                    f"Database path {db_path} appears to be on a "
                                    "network filesystem, which may cause locking issues"
                                )
                    except (OSError, AttributeError):
                        # statvfs not available or failed, continue
                        pass
            
            # Test file locking (critical for SQLite)
            import fcntl
            with test_file.open('r+b') as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except (OSError, IOError):
                    raise ValidationError(
                        f"File locking test failed for {db_path}. "
                        "This may indicate a network filesystem."
                    )
                        
        finally:
            # Clean up test file
            try:
                test_file.unlink()
            except FileNotFoundError:
                pass
                
    except ValidationError:
        raise
    except Exception as e:
        logger.warning(f"Database path validation warning: {e}")
        # Don't fail on validation errors in development




def get_database_url(db_path = None, use_encryption: bool = True) -> str:
    """
    Build the database URL with optional SQLCipher encryption parameters.
    
    Args:
        db_path: Optional custom database path. Defaults to data/walnut.db
        use_encryption: Whether to use SQLCipher encryption (requires pysqlcipher3)
        
    Returns:
        str: SQLAlchemy database URL with optional encryption parameters
    """
    if db_path is None:
        # Default to data directory
        base_dir = Path.cwd()
        data_dir = base_dir / "data"
        data_dir.mkdir(exist_ok=True)  
        db_path = data_dir / "walnut.db"
    else:
        # Ensure db_path is a Path object
        if isinstance(db_path, str):
            db_path = Path(db_path)
    
    # Validate database path
    validate_database_path(db_path)
    
    if use_encryption and SQLCIPHER_AVAILABLE:
        # Get master key for encryption
        master_key = get_master_key()
        
        # Create encrypted database file if it doesn't exist
        _ensure_encrypted_database(db_path, master_key)
        
        # Use the registered sqlite.sqlcipher dialect
        db_url = f"sqlite+sqlcipher:///{db_path}?key={quote(master_key)}"
        logger.info(f"SQLCipher encrypted database configured for: {db_path}")
    else:
        if use_encryption and not SQLCIPHER_AVAILABLE:
            logger.warning(
                "SQLCipher encryption requested but pysqlcipher3 not available. "
                "Using unencrypted database."
            )
        
        # Build standard SQLite URL using aiosqlite
        db_url = f"sqlite+aiosqlite:///{db_path}"
        logger.info(f"Standard database URL configured for: {db_path}")
    
    return db_url


async def configure_sqlite_connection(connection: aiosqlite.Connection) -> None:
    """
    Configure SQLite connection with WAL mode and performance settings.
    
    Args:
        connection: aiosqlite connection to configure
    """
    # Enable WAL mode for concurrent access  
    await connection.execute("PRAGMA journal_mode=WAL")
    
    # Set busy timeout to 5 seconds
    await connection.execute("PRAGMA busy_timeout=5000")
    
    # Enable foreign key constraints
    await connection.execute("PRAGMA foreign_keys=ON")
    
    # Optimize for performance
    await connection.execute("PRAGMA synchronous=NORMAL")  # WAL allows NORMAL
    await connection.execute("PRAGMA cache_size=10000")    # 10MB cache
    await connection.execute("PRAGMA temp_store=MEMORY")   # Use memory for temp
    
    # Enable query optimization
    await connection.execute("PRAGMA optimize")
    
    logger.debug("SQLite connection configured with WAL mode and optimizations")


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Set SQLite pragmas for synchronous connections (used by Alembic).
    
    This event listener configures SQLite connections that aren't async.
    Also handles SQLCipher decryption if encryption key is present in URL.
    """
    cursor = dbapi_connection.cursor()
    
    # Check if this is an encrypted database connection
    if hasattr(connection_record, 'info') and 'encryption_key' in connection_record.info:
        encryption_key = connection_record.info['encryption_key']
        logger.debug("Setting up SQLCipher decryption for sync connection")
        escaped_key = encryption_key.replace("'", "''")
        cursor.execute(f"PRAGMA key = '{escaped_key}'")
    
    # Enable WAL mode
    cursor.execute("PRAGMA journal_mode=WAL")
    
    # Set busy timeout
    cursor.execute("PRAGMA busy_timeout=5000")
    
    # Enable constraints
    cursor.execute("PRAGMA foreign_keys=ON")
    
    # Performance settings
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=10000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    
    cursor.close()


# Custom connection event handler for async connections
def _setup_encrypted_connection(connection, encryption_key: str):
    """
    Set up SQLCipher decryption for a database connection.
    
    This function is called for each new connection to configure
    the encryption key and database settings.
    """
    cursor = connection.cursor()
    
    # Set encryption key first
    escaped_key = encryption_key.replace("'", "''")
    cursor.execute(f"PRAGMA key = '{escaped_key}'")
    
    # Configure database settings
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=10000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    
    cursor.close()
    logger.debug("SQLCipher connection configured with encryption key")


def create_database_engine(
    db_path = None,
    echo: bool = False,
    pool_size: int = 20,
    max_overflow: int = 0,
    use_encryption: bool = True,
) -> Any:  # Return type can be AsyncEngine or AsyncSQLCipherEngine
    """
    Create an async SQLAlchemy engine with optional SQLCipher encryption.
    
    Args:
        db_path: Optional database file path
        echo: Whether to echo SQL statements (for debugging)
        pool_size: Maximum number of connections in pool
        max_overflow: Maximum overflow connections beyond pool_size
        use_encryption: Whether to use SQLCipher encryption
        
    Returns:
        AsyncEngine or AsyncSQLCipherEngine: Configured async database engine
        
    Raises:
        DatabaseError: If engine creation fails
    """
    try:
        db_url = get_database_url(db_path, use_encryption)
        
        # Check if this is a SQLCipher URL that needs special handling
        if use_encryption and SQLCIPHER_AVAILABLE and "sqlcipher" in db_url:
            # Use our custom async SQLCipher engine wrapper
            from .async_engine_wrapper import create_async_sqlcipher_engine
            
            logger.info("Creating async SQLCipher engine with thread pool wrapper")
            engine = create_async_sqlcipher_engine(db_url, echo)
            
            logger.info(
                f"SQLCipher async engine created for encrypted database"
            )
            return engine
        
        # Standard SQLAlchemy async engine for non-encrypted databases
        engine_kwargs = {
            "echo": echo,
        }
        
        # SQLite-specific configuration
        if "sqlite" in db_url:
            engine_kwargs.update({
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            })
        else:
            # Non-SQLite databases can use connection pooling
            engine_kwargs.update({
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_timeout": 30,
                "pool_recycle": 3600,
            })
        
        # Create async engine
        engine = create_async_engine(db_url, **engine_kwargs)
        
        # Store original URL for verification purposes
        engine._original_url = db_url
        
        logger.info(
            f"Standard async database engine created with pool_size={pool_size}, "
            f"max_overflow={max_overflow}"
        )
        return engine
        
    except Exception as e:
        logger.error(f"Failed to create database engine: {e}")
        raise DatabaseError(f"Database engine creation failed: {e}") from e


async def check_database_connection(engine: Any) -> Dict[str, Any]:
    """
    Test database connection and return diagnostic information.
    
    Args:
        engine: Database engine to test
        
    Returns:
        Dict containing connection test results and diagnostics
        
    Raises:
        DatabaseError: If connection test fails
    """
    try:
        # Check if this is our custom SQLCipher engine
        if hasattr(engine, 'database_path') and hasattr(engine, 'encryption_key'):
            # Use custom SQLCipher engine test
            from .async_engine_wrapper import test_async_sqlcipher_engine
            return await test_async_sqlcipher_engine(engine)
        
        # Standard SQLAlchemy engine
        async with engine.begin() as conn:
            # Test basic connectivity
            result = await conn.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            
            # Get SQLite version and encryption status
            version_result = await conn.execute(text("SELECT sqlite_version()"))
            sqlite_version = version_result.scalar()
            
            # Test encryption (SQLCipher specific)
            cipher_version = None
            encryption_enabled = False
            
            try:
                cipher_result = await conn.execute(text("PRAGMA cipher_version"))
                cipher_version = cipher_result.scalar()
                encryption_enabled = True
            except Exception:
                # Check if this is a SQLCipher database by looking at URL
                if "sqlcipher" in str(engine.url):
                    encryption_enabled = True
                    cipher_version = "SQLCipher (version check failed)"
                
            # Get journal mode
            journal_result = await conn.execute(text("PRAGMA journal_mode"))
            journal_mode = journal_result.scalar()
            
            # Get database file size if possible
            try:
                size_result = await conn.execute(text("PRAGMA page_count"))
                page_count = size_result.scalar()
                page_size_result = await conn.execute(text("PRAGMA page_size"))
                page_size = page_size_result.scalar()
                db_size = page_count * page_size if page_count and page_size else None
            except Exception:
                db_size = None
            
            # Additional SQLCipher verification
            sqlcipher_verified = False
            # Check if this is an encrypted database by looking for our custom URL parameter
            original_url = getattr(engine, '_original_url', str(engine.url))
            if encryption_enabled and "encryption_key=" in original_url:
                try:
                    # Try to get database path for encryption test
                    db_path = str(engine.url).split("://")[-1].split("?")[0]
                    if db_path and Path(db_path).exists():
                        # Run encryption verification test with the encryption key
                        try:
                            encryption_key = get_master_key()
                            encryption_test = test_sqlcipher_encryption(db_path, encryption_key)
                            sqlcipher_verified = encryption_test['encryption_verified']
                        except Exception as key_error:
                            logger.warning(f"Could not retrieve encryption key for verification: {key_error}")
                except Exception as e:
                    logger.warning(f"SQLCipher verification failed: {e}")
            
            diagnostics = {
                "connection_test": test_value == 1,
                "sqlite_version": sqlite_version,
                "cipher_version": cipher_version,
                "journal_mode": journal_mode,
                "encryption_enabled": encryption_enabled,
                "sqlcipher_verified": sqlcipher_verified,
                "database_size_bytes": db_size,
                "wal_mode_enabled": journal_mode == "wal",
                "database_url_type": "sqlcipher" if "encryption_key=" in getattr(engine, '_original_url', str(engine.url)) else "sqlite",
            }
            
            logger.info("Database connection test successful")
            if encryption_enabled:
                logger.info(f"SQLCipher encryption: {'VERIFIED' if sqlcipher_verified else 'ENABLED'}")
            logger.debug(f"Database diagnostics: {diagnostics}")
            
            return diagnostics
            
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        raise DatabaseError(f"Connection test failed: {e}") from e


async def cleanup_database_engine(engine: AsyncEngine) -> None:
    """
    Properly cleanup database engine and connections.
    
    Args:
        engine: Database engine to cleanup
    """
    try:
        await engine.dispose()
        logger.info("Database engine disposed successfully")
    except Exception as e:
        logger.error(f"Error during database engine cleanup: {e}")