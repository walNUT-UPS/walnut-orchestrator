"""
Provides database session management for FastAPI and async context managers.
"""
from contextlib import asynccontextmanager
import logging
import anyio
from .engine import SessionLocal

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_db_session():
    """Async context manager for database sessions."""
    session = SessionLocal()
    try:
        logger.debug("DB session opened")
        yield session
        # Use anyio.to_thread.run_sync for sync methods
        await anyio.to_thread.run_sync(session.commit)
        logger.debug("DB session committed")
    except Exception:
        # Use anyio.to_thread.run_sync for sync methods
        await anyio.to_thread.run_sync(session.rollback)
        logger.exception("DB session rolled back due to error")
        raise
    finally:
        # Use anyio.to_thread.run_sync for sync methods
        await anyio.to_thread.run_sync(session.close)
        logger.debug("DB session closed")

def get_db_session_dependency():
    """FastAPI dependency for database sessions."""
    session = SessionLocal()
    try:
        logger.debug("DB session opened (dependency)")
        yield session
        session.commit()
        logger.debug("DB session committed (dependency)")
    except Exception:
        session.rollback()
        logger.exception("DB session rolled back due to error (dependency)")
        raise
    finally:
        session.close()
        logger.debug("DB session closed (dependency)")
