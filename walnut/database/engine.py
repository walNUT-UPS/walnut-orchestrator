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
KEY = os.environ["WALNUT_DB_KEY"]  # must be set

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
    escaped_key = KEY.replace("'", "''")
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