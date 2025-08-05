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

logger = logging.getLogger(__name__)


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


def get_database_url(db_path: Optional[Path] = None) -> str:
    """
    Build the database URL with SQLCipher encryption parameters.
    
    Args:
        db_path: Optional custom database path. Defaults to data/walnut.db
        
    Returns:
        str: SQLAlchemy database URL with encryption parameters
    """
    if db_path is None:
        # Default to data directory
        base_dir = Path.cwd()
        data_dir = base_dir / "data"
        data_dir.mkdir(exist_ok=True)  
        db_path = data_dir / "walnut.db"
    
    # Validate database path
    validate_database_path(db_path)
    
    # Get master key
    master_key = get_master_key()
    
    # URL encode the key to handle special characters
    encoded_key = quote(master_key)
    
    # Build SQLCipher URL with encryption parameters
    db_url = (
        f"sqlite+aiosqlite:///{db_path}"
        f"?uri=true"
        f"&key={encoded_key}"
        f"&cipher=aes-256-cbc"
        f"&kdf_iter=64000"
    )
    
    logger.info(f"Database URL configured for: {db_path}")
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
    """
    cursor = dbapi_connection.cursor()
    
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


def create_database_engine(
    db_path: Optional[Path] = None,
    echo: bool = False,
    pool_size: int = 20,
    max_overflow: int = 0,
) -> AsyncEngine:
    """
    Create an async SQLAlchemy engine with SQLCipher encryption.
    
    Args:
        db_path: Optional database file path
        echo: Whether to echo SQL statements (for debugging)
        pool_size: Maximum number of connections in pool
        max_overflow: Maximum overflow connections beyond pool_size
        
    Returns:
        AsyncEngine: Configured async SQLAlchemy engine
        
    Raises:
        DatabaseError: If engine creation fails
    """
    try:
        db_url = get_database_url(db_path)
        
        # Configure engine parameters based on database type
        engine_kwargs = {
            "echo": echo,
        }
        
        # SQLite-specific configuration
        if "sqlite" in db_url:
            engine_kwargs.update({
                "poolclass": StaticPool,
                "connect_args": {
                    "check_same_thread": False,
                    "timeout": 30,
                },
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
        
        logger.info(
            f"Database engine created with pool_size={pool_size}, "
            f"max_overflow={max_overflow}"
        )
        return engine
        
    except Exception as e:
        logger.error(f"Failed to create database engine: {e}")
        raise DatabaseError(f"Database engine creation failed: {e}") from e


async def test_database_connection(engine: AsyncEngine) -> Dict[str, Any]:
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
        async with engine.begin() as conn:
            # Test basic connectivity
            result = await conn.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            
            # Get SQLite version and encryption status
            version_result = await conn.execute(text("SELECT sqlite_version()"))
            sqlite_version = version_result.scalar()
            
            # Test encryption (SQLCipher specific)
            try:
                cipher_result = await conn.execute(text("PRAGMA cipher_version"))
                cipher_version = cipher_result.scalar()
            except Exception:
                cipher_version = None
                
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
            
            diagnostics = {
                "connection_test": test_value == 1,
                "sqlite_version": sqlite_version,
                "cipher_version": cipher_version,
                "journal_mode": journal_mode,
                "encryption_enabled": cipher_version is not None,
                "database_size_bytes": db_size,
                "wal_mode_enabled": journal_mode == "wal",
            }
            
            logger.info("Database connection test successful")
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