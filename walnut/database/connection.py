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
        await anyio.to_thread.run_sync(session.commit)
    except Exception:
        await anyio.to_thread.run_sync(session.rollback)
        raise
    finally:
        await anyio.to_thread.run_sync(session.close)