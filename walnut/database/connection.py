"""
Provides database session management for FastAPI and async context managers.
"""
from contextlib import asynccontextmanager
import anyio
from .engine import SessionLocal

@asynccontextmanager
async def get_db_session():
    """Async context manager for database sessions."""
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

async def get_db_session_dependency():
    """FastAPI dependency for database sessions."""
    session = SessionLocal()
    try:
        yield session
    finally:
        # Use anyio.to_thread.run_sync for sync session methods
        import anyio
        await anyio.to_thread.run_sync(session.close)