"""
Database engine configuration for synchronous access with SQLCipher.
"""
import logging
import os
import os.path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects import registry

# Register the SQLCipher dialect
registry.register("sqlcipher", "walnut.database.sqlcipher_dialect", "SQLCipherDialect")

engine = None
SessionLocal = None
logger = logging.getLogger(__name__)

def get_db_key():
    """Get database key with user-friendly error handling."""
    key = os.environ.get("WALNUT_DB_KEY")
    if not key:
        raise ValueError(
            "Missing WALNUT_DB_KEY environment variable.\n"
            "Please set the database encryption key (minimum 32 characters):\n"
            "  export WALNUT_DB_KEY=\"your_32_character_encryption_key_here\""
        )
    if len(key) < 32:
        raise ValueError(
            f"WALNUT_DB_KEY must be at least 32 characters (current: {len(key)})\n"
            "Please set a longer encryption key:\n"
            "  export WALNUT_DB_KEY=\"your_32_character_encryption_key_here\""
        )
    return key

def init_db(db_path: str):
    """Initializes the database engine and session factory."""
    global engine, SessionLocal
    logger.info("Initializing SQLCipher database at %s", db_path)

    def _sqlcipher_creator():
        import pysqlcipher3.dbapi2 as sqlcipher

        conn = sqlcipher.connect(
            db_path,
            check_same_thread=False,
            timeout=30.0,
            detect_types=0,
        )
        key = get_db_key()
        escaped_key = key.replace("'", "''")
        conn.execute(f"PRAGMA key = '{escaped_key}'")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    engine = create_engine(
        f"sqlcipher:///{db_path}",
        creator=_sqlcipher_creator,
        pool_pre_ping=True,
        future=True,
    )

    SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    logger.info("Database engine initialized")

# Initialize with default path for production
DB_PATH_DEFAULT = os.path.abspath("data/walnut.db")
if not os.environ.get("WALNUT_TESTING"):
    # Ensure the data directory exists
    os.makedirs(os.path.dirname(DB_PATH_DEFAULT), exist_ok=True)
    init_db(DB_PATH_DEFAULT)
