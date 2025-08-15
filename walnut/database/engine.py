"""
Database engine configuration for synchronous access with SQLCipher.
"""
import os
import os.path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects import registry

# Register the SQLCipher dialect
registry.register("sqlcipher", "walnut.database.sqlcipher_dialect", "SQLCipherDialect")

DB_PATH = os.path.abspath("data/walnut.db")

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

def _sqlcipher_creator():
    # Import here to avoid circular imports
    import pysqlcipher3.dbapi2 as sqlcipher
    
    # Open the encrypted DB directly; don't let SQLAlchemy call connect().
    conn = sqlcipher.connect(
        DB_PATH,
        check_same_thread=False,  # do this here; 'connect_args' is ignored with creator
        timeout=30.0,
        detect_types=0,
    )

    # If your DB was created with SQLCipher 3 formats, keep 3; otherwise try 4.
    conn.execute("PRAGMA cipher_compatibility = 3")

    # Always parameterize; no manual escaping.
    key = get_db_key()
    escaped_key = key.replace("'", "''")
    conn.execute(f"PRAGMA key = '{escaped_key}'")

    # Your usual pragmas
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    return conn

# Use SQLCipher dialect which properly handles supports_regexp = False
engine = create_engine(
    f"sqlcipher:///{DB_PATH}",
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