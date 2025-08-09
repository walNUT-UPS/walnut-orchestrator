import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import os
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

@pytest.fixture
async def async_client():
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client

def get_current_admin_user_override():
    return {"username": "testadmin", "roles": ["admin"]}



@pytest_asyncio.fixture(scope="function")
async def test_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        os.environ["WALNUT_DB_KEY"] = "a-test-key-that-is-long-enough-for-sqlcipher"
        os.environ["WALNUT_JWT_SECRET"] = "test-secret"

        # Set up alembic config
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite+async_sqlcipher:///{db_path}?encryption_key={os.environ['WALNUT_DB_KEY']}")

        # Upgrade the database to the latest revision
        command.upgrade(alembic_cfg, "head")

        # Yield the database path
        yield str(db_path)
        # Unset the env var to avoid side effects
        if "WALNUT_DB_PATH" in os.environ:
            del os.environ["WALNUT_DB_PATH"]


@pytest_asyncio.fixture(scope="function")
async def async_client(test_db):
    """
    A fixture that provides an httpx.AsyncClient for testing the API.
    """
    os.environ["WALNUT_DB_PATH"] = test_db
    os.environ["WALNUT_ALLOWED_ORIGINS"] = "http://test.com"
    os.environ["WALNUT_SIGNUP_ENABLED"] = "true"

    await init_database(db_path=test_db, create_tables=False)

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    await close_database()

