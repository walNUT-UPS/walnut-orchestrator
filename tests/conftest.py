import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import os

# Set dummy environment variables before any modules are imported
os.environ["WALNUT_DB_KEY"] = "a-dummy-key-that-is-long-enough-for-testing"
os.environ["WALNUT_JWT_SECRET"] = "a-dummy-secret-for-testing"
import tempfile
from pathlib import Path
from httpx import AsyncClient
from walnut.app import app
from walnut.database.connection import init_database, close_database
from alembic.config import Config
from alembic import command



@pytest_asyncio.fixture
async def mock_db_session():
    session = AsyncMock()
    # Configure common async methods
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    # Context manager support
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session

@pytest_asyncio.fixture
async def mock_engine():
    engine = MagicMock()
    engine.begin = AsyncMock()
    engine.connect = AsyncMock()
    return engine

@pytest.fixture
def mock_create_database_engine(mock_engine):
    with patch('walnut.database.engine.create_database_engine') as mock:
        mock.return_value = mock_engine
        yield mock

@pytest.fixture
def mock_session_factory(mock_db_session):
    factory = MagicMock()
    factory.return_value = mock_db_session

    # For async context manager usage
    async def async_session_context():
        return mock_db_session

    factory.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory

from click.testing import CliRunner
import httpx
from walnut.app import app

@pytest.fixture
def cli_runner():
    return CliRunner()

def get_current_admin_user_override():
    return {"username": "testadmin", "roles": ["admin"]}

@pytest_asyncio.fixture(scope="function")
async def test_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        key = "a-test-key-that-is-long-enough-for-sqlcipher"
        os.environ["WALNUT_DB_KEY"] = key
        os.environ["WALNUT_JWT_SECRET"] = "test-secret"

        # Set up alembic config for the test database
        alembic_cfg = Config("alembic.ini")
        # Use the correct dialect: sqlite+sqlcipher
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite+sqlcipher:///{db_path}?key={key}")

        # In a real async context, command.upgrade should be run with asyncio.to_thread
        # For testing purposes, we run it synchronously before the app starts.
        command.upgrade(alembic_cfg, "head")

        yield str(db_path)

        # Clean up env vars
        del os.environ["WALNUT_DB_KEY"]
        del os.environ["WALNUT_JWT_SECRET"]

@pytest_asyncio.fixture(scope="function")
async def async_client(test_db):
    """
    A fixture that provides an httpx.AsyncClient for testing the API,
    with a fully initialized database.
    """
    # Set environment variables for the application to use during the test
    os.environ["WALNUT_DB_PATH"] = test_db
    os.environ["WALNUT_ALLOWED_ORIGINS"] = "http://test.com,http://localhost"
    os.environ["WALNUT_SIGNUP_ENABLED"] = "true"

    # The database schema is already created by alembic in the test_db fixture
    # We just need to initialize the connection manager
    await init_database(db_path=Path(test_db), create_tables=False)

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    await close_database()

    # Clean up env vars
    del os.environ["WALNUT_DB_PATH"]
    del os.environ["WALNUT_ALLOWED_ORIGINS"]
    del os.environ["WALNUT_SIGNUP_ENABLED"]

