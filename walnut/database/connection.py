"""
Database connection management and pooling for walNUT.

This module provides high-level database connection management including:
- Connection pool lifecycle management
- Transaction contexts
- Database health monitoring
- Connection retry logic
- Graceful shutdown handling
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlalchemy.sql import text

from .engine import (
    DatabaseError,
    cleanup_database_engine,
    create_database_engine,
    check_database_connection,
)
from .models import Base

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages database connections and provides high-level database operations.
    
    This class handles:
    - Engine lifecycle management
    - Session factory creation
    - Connection health monitoring
    - Graceful shutdown procedures
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        echo: bool = False,
        pool_size: int = 20,
        max_overflow: int = 0,
    ):
        """
        Initialize connection manager.
        
        Args:
            db_path: Optional database file path
            echo: Whether to echo SQL statements
            pool_size: Maximum connections in pool
            max_overflow: Maximum overflow connections
        """
        self.db_path = db_path
        self.echo = echo
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
    @property
    def engine(self) -> AsyncEngine:
        """Get the database engine, creating it if necessary."""
        if self._engine is None:
            raise DatabaseError("Database engine not initialized. Call startup() first.")
        return self._engine
    
    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get the session factory, creating it if necessary."""
        if self._session_factory is None:
            raise DatabaseError("Session factory not initialized. Call startup() first.")
        return self._session_factory
    
    async def startup(self) -> Dict[str, Any]:
        """
        Initialize database engine and perform startup checks.
        
        Returns:
            Dict containing startup diagnostics
            
        Raises:
            DatabaseError: If startup fails
        """
        try:
            logger.info("Starting database connection manager")
            
            # Create database engine
            self._engine = create_database_engine(
                db_path=self.db_path,
                echo=self.echo,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
            )
            
            # Create session factory
            self._session_factory = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=True,
                autocommit=False,
            )
            
            # Test connection and get diagnostics
            diagnostics = await check_database_connection(self._engine)
            
            # Start health monitoring
            self._health_check_task = asyncio.create_task(
                self._health_check_loop()
            )
            
            logger.info("Database connection manager started successfully")
            return diagnostics
            
        except Exception as e:
            logger.error(f"Database startup failed: {e}")
            await self.shutdown()
            raise DatabaseError(f"Database startup failed: {e}") from e
    
    async def shutdown(self) -> None:
        """
        Gracefully shutdown database connections and cleanup resources.
        """
        logger.info("Shutting down database connection manager")
        
        # Signal shutdown to background tasks
        self._shutdown_event.set()
        
        # Cancel health check task
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Cleanup engine
        if self._engine:
            await cleanup_database_engine(self._engine)
            self._engine = None
        
        # Clear session factory
        self._session_factory = None
        
        logger.info("Database connection manager shutdown complete")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session with automatic cleanup.
        
        Yields:
            AsyncSession: Database session
            
        Raises:
            DatabaseError: If session creation fails
        """
        if self._session_factory is None:
            raise DatabaseError("Connection manager not initialized")
        
        session = self._session_factory()
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()
    
    @asynccontextmanager
    async def get_transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session with automatic transaction management.
        
        Commits on success, rolls back on exception.
        
        Yields:
            AsyncSession: Database session in transaction
        """
        async with self.get_session() as session:
            async with session.begin():
                yield session
    
    async def execute_raw_sql(
        self, 
        sql: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Execute raw SQL with parameters.
        
        Args:
            sql: SQL statement to execute
            parameters: Optional parameters for the SQL
            
        Returns:
            Query result
        """
        async with self.get_session() as session:
            result = await session.execute(
                text(sql), 
                parameters or {}
            )
            await session.commit()
            return result
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform database health check.
        
        Returns:
            Dict containing health status and metrics
        """
        try:
            if not self._engine:
                return {
                    "healthy": False,
                    "error": "Engine not initialized",
                }
            
            # Test basic connectivity
            diagnostics = await check_database_connection(self._engine)
            
            # Get pool status (handle different pool types)
            try:
                pool = self._engine.pool
                pool_status = {}
                
                try:
                    # Try to get standard pool metrics
                    pool_status.update({
                        "size": getattr(pool, 'size', lambda: 0)(),
                        "checked_in": getattr(pool, 'checkedin', lambda: 0)(),
                        "checked_out": getattr(pool, 'checkedout', lambda: 0)(),
                        "overflow": getattr(pool, 'overflow', lambda: 0)(),
                        "invalid": getattr(pool, 'invalid', lambda: 0)(),
                    })
                except Exception:
                    # Fallback for pools that don't support these methods
                    pool_status = {
                        "pool_class": pool.__class__.__name__,
                        "status": "active",
                    }
            except AttributeError:
                # Handle engines without pool attribute
                pool_status = {
                    "pool_class": "unavailable",
                    "status": "active",
                }
            
            return {
                "healthy": True,
                "engine_diagnostics": diagnostics,
                "pool_status": pool_status,
                "connection_string": str(self._engine.url).split("?")[0],  # Hide credentials
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "healthy": False,
                "error": str(e),
            }
    
    async def _health_check_loop(self) -> None:
        """
        Background task for periodic health checks.
        """
        logger.info("Starting database health check loop")
        
        while not self._shutdown_event.is_set():
            try:
                # Wait for next check or shutdown signal
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=300  # 5 minutes
                )
                break  # Shutdown requested
                
            except asyncio.TimeoutError:
                # Perform health check
                try:
                    health_status = await self.health_check()
                    if not health_status["healthy"]:
                        logger.warning(
                            f"Database health check failed: {health_status.get('error')}"
                        )
                    else:
                        logger.debug("Database health check passed")
                        
                except Exception as e:
                    logger.error(f"Health check error: {e}")
                    
        logger.info("Database health check loop stopped")
    
    async def create_tables(self) -> None:
        """
        Create all database tables.
        
        Raises:
            DatabaseError: If table creation fails
        """
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise DatabaseError(f"Table creation failed: {e}") from e
    
    async def drop_tables(self) -> None:
        """
        Drop all database tables.
        
        WARNING: This will delete all data!
        
        Raises:
            DatabaseError: If table dropping fails
        """
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            logger.info("Database tables dropped successfully")
            
        except Exception as e:
            logger.error(f"Failed to drop database tables: {e}")
            raise DatabaseError(f"Table dropping failed: {e}") from e


# Global connection manager instance
_connection_manager: Optional[ConnectionManager] = None


async def get_connection_manager() -> ConnectionManager:
    """
    Get the global connection manager instance.
    
    Returns:
        ConnectionManager: Global connection manager
        
    Raises:
        DatabaseError: If connection manager not initialized
    """
    global _connection_manager
    
    if _connection_manager is None:
        raise DatabaseError(
            "Connection manager not initialized. Call init_database() first."
        )
    
    return _connection_manager


async def init_database(
    db_path: Optional[str] = None,
    echo: bool = False,
    pool_size: int = 20,
    max_overflow: int = 0,
    create_tables: bool = True,
) -> Dict[str, Any]:
    """
    Initialize the global database connection manager.
    
    Args:
        db_path: Optional database file path
        echo: Whether to echo SQL statements
        pool_size: Maximum connections in pool
        max_overflow: Maximum overflow connections
        create_tables: Whether to create tables on startup
        
    Returns:
        Dict containing initialization diagnostics
        
    Raises:
        DatabaseError: If initialization fails
    """
    global _connection_manager
    
    if _connection_manager is not None:
        logger.warning("Database already initialized, shutting down existing connection")
        await _connection_manager.shutdown()
    
    _connection_manager = ConnectionManager(
        db_path=db_path,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )
    
    diagnostics = await _connection_manager.startup()
    
    if create_tables:
        await _connection_manager.create_tables()
    
    return diagnostics


async def close_database() -> None:
    """
    Close the global database connection manager.
    """
    global _connection_manager
    
    if _connection_manager is not None:
        await _connection_manager.shutdown()
        _connection_manager = None


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session from the global connection manager.
    
    Yields:
        AsyncSession: Database session
    """
    manager = await get_connection_manager()
    async with manager.get_session() as session:
        yield session


@asynccontextmanager
async def get_db_transaction() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database transaction from the global connection manager.
    
    Yields:
        AsyncSession: Database session in transaction
    """
    manager = await get_connection_manager()
    async with manager.get_transaction() as session:
        yield session


async def execute_sql(
    sql: str, 
    parameters: Optional[Dict[str, Any]] = None
) -> Any:
    """
    Execute raw SQL using the global connection manager.
    
    Args:
        sql: SQL statement to execute
        parameters: Optional parameters
        
    Returns:
        Query result
    """
    manager = await get_connection_manager()
    return await manager.execute_raw_sql(sql, parameters)


async def get_database_health() -> Dict[str, Any]:
    """
    Get database health status from the global connection manager.
    
    Returns:
        Dict containing health status
    """
    try:
        manager = await get_connection_manager()
        return await manager.health_check()
    except DatabaseError:
        return {
            "healthy": False,
            "error": "Connection manager not initialized",
        }