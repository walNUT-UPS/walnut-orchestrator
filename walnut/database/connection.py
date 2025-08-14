"""
Provides a simple async context manager for database sessions.
"""
from contextlib import asynccontextmanager
import anyio
from .engine import SessionLocal

@asynccontextmanager
async def get_db_session():
    session = SessionLocal()
    try:
        yield session
        # Use anyio.to_thread.run_sync for sync methods
        await anyio.to_thread.run_sync(session.commit)
    except Exception:
        # Use anyio.to_thread.run_sync for sync methods
        await anyio.to_thread.run_sync(session.rollback)
        raise
    finally:
        # Use anyio.to_thread.run_sync for sync methods
        await anyio.to_thread.run_sync(session.close)