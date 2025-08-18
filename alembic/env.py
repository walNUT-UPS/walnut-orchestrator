"""
Alembic environment configuration for walNUT database migrations.
"""
import asyncio
from logging.config import fileConfig
from pathlib import Path
import os

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add the walnut package to the path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from walnut.database.models import Base
from walnut.auth.models import User  # Ensure the User model is imported

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a database connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' async mode."""
    # this is the Alembic Config object, which provides
    # access to the values within the .ini file in use.
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # This is for pytest-asyncio, which runs an event loop for the tests.
        # We need to schedule the migrations in the existing loop.
        # A simple way is to create a task and then let the test runner await it.
        # However, alembic's script is synchronous, so we have to block here.
        # A common pattern is to use a nested event loop library like `nest_asyncio`,
        # but to avoid adding a dependency, we'll try a simpler approach.
        # We can't use loop.run_until_complete if the loop is already running.
        # The issue is a fundamental conflict between sync alembic command and async pytest.
        # Let's try to run the async migrations in a new thread with its own loop.
        from threading import Thread
        thread = Thread(target=asyncio.run, args=(run_async_migrations(),))
        thread.start()
        thread.join()
    else:
        asyncio.run(run_async_migrations())