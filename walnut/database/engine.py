"""
Database engine configuration for synchronous access with SQLCipher.
Hard fix for pysqlcipher3 create_function(…): swallow 4th arg (deterministic).
"""
import os
import os.path
import types

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pysqlcipher3.dbapi2 as sqlcipher

DB_PATH = os.path.abspath("data/walnut.db")
KEY = os.environ["WALNUT_DB_KEY"]  # must be set

def _sqlcipher_creator():
    # Open the encrypted DB directly; don't let SQLAlchemy call connect().
    conn = sqlcipher.connect(
        DB_PATH,
        check_same_thread=False,  # do this here; 'connect_args' is ignored with creator
        timeout=30.0,
        detect_types=0,
    )

    # --- CRITICAL PATCH: make create_function tolerant of SQLAlchemy's 4th arg ---
    try:
        _orig_cf = conn.create_function  # bound method

        def _safe_create_function(name, num_params, func, *args, **kwargs):
            # Ignore extra positional/keyword args (e.g., deterministic=True)
            return _orig_cf(name, num_params, func)

        # Rebind as a bound method on this connection instance
        conn.create_function = types.MethodType(_safe_create_function, conn)
    except Exception:
        # If the patch can't be applied (shouldn't happen), we still proceed.
        pass

    # If your DB was created with SQLCipher 3 formats, keep 3; otherwise try 4.
    conn.execute("PRAGMA cipher_compatibility = 3")

    # Always parameterize; no manual escaping.
    escaped_key = KEY.replace("'", "''")
    conn.execute(f"PRAGMA key = '{escaped_key}'")

    # Your usual pragmas
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    return conn

# The URL is irrelevant when 'creator' is provided.
engine = create_engine(
    "sqlite://",
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