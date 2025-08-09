"""
Alembic environment configuration for walNUT database migrations.

This module configures Alembic to work with SQLCipher encrypted databases
and provides both online and offline migration capabilities.
"""

import asyncio
import logging
import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from walnut.database.engine import create_database_engine

from alembic import context

# Add the walnut package to the path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from walnut.database.models import Base
from walnut.auth.models import User  # Ensure the User model is imported for autogeneration
from walnut.database.engine import get_database_url, set_sqlite_pragma

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger('alembic.env')

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_database_config():
    """
    Get database configuration for Alembic.
    
    Returns the database URL with proper SQLCipher configuration.
    """
    try:
        # Get database URL with encryption
        db_url = get_database_url()
        logger.info("Using encrypted database URL for migrations")
        return db_url
    except Exception as e:
        logger.error(f"Failed to get database configuration: {e}")
        raise


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    try:
        url = get_database_config()
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            # SQLite specific options
            render_as_batch=True,  # Enable batch mode for SQLite
            compare_type=True,     # Compare column types
            compare_server_default=True,  # Compare server defaults
        )

        with context.begin_transaction():
            context.run_migrations()
            
    except Exception as e:
        logger.error(f"Offline migration failed: {e}")
        raise


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations with a database connection.
    
    Args:
        connection: SQLAlchemy connection object
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite specific options
        render_as_batch=True,      # Enable batch mode for SQLite ALTER TABLE support
        compare_type=True,         # Compare column types during autogenerate
        compare_server_default=True,  # Compare server defaults
        # Include object filters to avoid system tables
        include_object=lambda object, name, type_, reflected, compare_to: not (
            type_ == "table" and name.startswith("sqlite_")
        ),
    )

    with context.begin_transaction():
        context.run_migrations()



async def run_async_migrations() -> None:
    """
    Run migrations in async mode for SQLCipher database.
    """
    try:
        # Create engine using the project's custom function
        connectable = create_database_engine()

        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

        await connectable.dispose()

    except Exception as e:
        logger.error(f"Async migration failed: {e}")
        raise


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    try:
        db_url = get_database_config()
        from sqlalchemy import create_engine
        engine = create_engine(db_url)

        with engine.connect() as connection:
            do_run_migrations(connection)
    except Exception as e:
        logger.error(f"Online migration failed: {e}")
        raise


# Determine migration mode
if context.is_offline_mode():
    logger.info("Running migrations in offline mode")
    run_migrations_offline()
else:
    logger.info("Running migrations in online mode")
    run_migrations_online()