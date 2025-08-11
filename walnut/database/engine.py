"""
Database engine configuration with SQLCipher encryption and WAL mode.
This module provides the core database engine setup for walNUT, including:
- SQLCipher AES-256 encryption via a custom SQLAlchemy dialect.
- Master key management from environment/Docker secrets.
- Local disk validation.
"""

import logging
import os
import stat
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

# Import SQLCipher dialect for registration
from . import sqlcipher_dialect

try:
    import pysqlcipher3.dbapi2 as sqlcipher
    SQLCIPHER_AVAILABLE = True
except ImportError:
    sqlcipher = None
    SQLCIPHER_AVAILABLE = False

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
    """
    # Try Docker secrets first
    secrets_path = Path("/run/secrets/walnut_db_key")
    if secrets_path.exists():
        try:
            key = secrets_path.read_text().strip()
            if key and len(key) >= 32:
                logger.info("Master key loaded from Docker secrets")
                return key
        except (OSError, IOError) as e:
            logger.warning(f"Failed to read Docker secret: {e}")

    # Fall back to environment variable
    key = os.getenv("WALNUT_DB_KEY")
    if key and len(key) >= 32:
        logger.info("Master key loaded from environment variable")
        return key

    # Development fallback
    dev_key = os.getenv("WALNUT_DB_KEY_DEV")
    if dev_key:
        logger.warning("Using development master key - NOT FOR PRODUCTION!")
        return dev_key

    raise EncryptionError(
        "No valid master key found. Set WALNUT_DB_KEY (32+ chars) or "
        "mount Docker secret at /run/secrets/walnut_db_key."
    )


def validate_database_path(db_path: Path) -> None:
    """
    Validate that the database path is on a local filesystem.
    """
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        test_file = db_path.parent / f".walnut_test_{os.getpid()}"
        try:
            test_file.touch()
            # Basic stat check
            stat_info = test_file.stat()
            # File locking test (critical for SQLite)
            import fcntl
            with test_file.open('r+b') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            test_file.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Database path validation failed with: {e}. "
                       "Ensure the path is on a local filesystem with proper permissions.")
        # Do not raise error, allow it to fail at connection time


def get_database_url(db_path: Optional[Path] = None, use_encryption: bool = True) -> str:
    """
    Build the database URL with optional SQLCipher encryption parameters.
    """
    if db_path is None:
        db_path = Path.cwd() / "data" / "walnut.db"
    
    validate_database_path(db_path)

    if use_encryption and SQLCIPHER_AVAILABLE:
        master_key = get_master_key()
        # Use the registered sqlite+sqlcipher dialect
        db_url = f"sqlite+sqlcipher:///{db_path}?key={quote(master_key)}"
        logger.info(f"SQLCipher encrypted database configured for: {db_path}")
    else:
        if use_encryption:
            logger.warning("SQLCipher requested but not available. Using unencrypted database.")
        # Build standard SQLite URL using aiosqlite
        db_url = f"sqlite+aiosqlite:///{db_path}"
        logger.info(f"Standard database URL configured for: {db_path}")

    return db_url


def create_database_engine(
    db_path: Optional[Path] = None,
    echo: bool = False,
    pool_size: int = 20,
    use_encryption: bool = True,
) -> AsyncEngine:
    """
    Create an async SQLAlchemy engine with optional SQLCipher encryption.
    """
    try:
        db_url = get_database_url(db_path, use_encryption)
        
        engine = create_async_engine(
            db_url,
            echo=echo,
            poolclass=StaticPool,  # Recommended for SQLite
        )

        logger.info(f"Async database engine created for URL: {engine.url.render_as_string(hide_password=True)}")
        return engine
        
    except Exception as e:
        logger.error(f"Failed to create database engine: {e}")
        raise DatabaseError(f"Database engine creation failed: {e}") from e


async def check_database_connection(engine: AsyncEngine) -> Dict[str, Any]:
    """
    Test database connection and return diagnostic information.
    """
    try:
        async with engine.connect() as conn:
            # Test basic connectivity
            result = await conn.execute(text("SELECT 1"))
            test_value = result.scalar_one()

            # Get SQLite version
            version_result = await conn.execute(text("SELECT sqlite_version()"))
            sqlite_version = version_result.scalar_one()

            # Test for SQLCipher
            cipher_version = None
            encryption_enabled = "sqlcipher" in engine.url.drivername
            if encryption_enabled:
                try:
                    cipher_result = await conn.execute(text("PRAGMA cipher_version"))
                    cipher_version = cipher_result.scalar_one_or_none()
                except Exception:
                    cipher_version = "unknown (pragma failed)"

            # Get journal mode
            journal_result = await conn.execute(text("PRAGMA journal_mode"))
            journal_mode = journal_result.scalar_one()
            
            diagnostics = {
                "connection_test": test_value == 1,
                "sqlite_version": sqlite_version,
                "encryption_enabled": encryption_enabled,
                "cipher_version": cipher_version,
                "journal_mode": journal_mode,
                "wal_mode_enabled": journal_mode == "wal",
            }
            logger.info("Database connection test successful.")
            return diagnostics
            
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        raise DatabaseError(f"Connection test failed: {e}") from e


async def cleanup_database_engine(engine: AsyncEngine) -> None:
    """
    Properly cleanup database engine and connections.
    """
    try:
        await engine.dispose()
        logger.info("Database engine disposed successfully")
    except Exception as e:
        logger.error(f"Error during database engine cleanup: {e}")