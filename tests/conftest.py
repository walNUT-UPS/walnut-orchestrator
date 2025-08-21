import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import os
import tempfile
from pathlib import Path
from httpx import AsyncClient
from walnut.app import app
from walnut.database.engine import init_db
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

import importlib
from httpx import Response, Request

@pytest.fixture
def cli_runner():
    return CliRunner()

@pytest_asyncio.fixture(scope="function")
async def oidc_async_client(test_db):
    """
    A dedicated async client for OIDC tests.
    It creates a custom app instance with OIDC settings enabled.
    """
    from walnut.config import Settings
    from walnut.app import create_app
    from walnut.database.engine import init_db

    test_settings = Settings(
        TESTING_MODE=True,
        DB_PATH=test_db,
        OIDC_ENABLED=True,
        OIDC_CLIENT_ID="test_client_id",
        OIDC_CLIENT_SECRET="test_client_secret",
        OIDC_DISCOVERY_URL="https://example.com/.well-known/openid-configuration",
        OIDC_ADMIN_ROLES=["admin"],
        OIDC_VIEWER_ROLES=["viewer"],
        JWT_SECRET="test-secret", # Must provide a JWT secret for the test settings
    )

    original_get = httpx.Client.get
    def mock_get(self, url, **kwargs):
        if str(url) == test_settings.OIDC_DISCOVERY_URL:
            response = Response(
                200,
                json={
                    "authorization_endpoint": "https://example.com/auth",
                    "token_endpoint": "https://example.com/token",
                    "userinfo_endpoint": "https://example.com/userinfo",
                },
            )
            response.request = Request("GET", url)
            return response
        return original_get(self, url, **kwargs)

    with patch("httpx.Client.get", new=mock_get):
        # Pass the custom settings object to the app factory
        app = create_app(settings_override=test_settings)
        init_db(test_db)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


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
    os.environ["WALNUT_TESTING"] = "true"
    os.environ["WALNUT_DB_PATH"] = test_db
    os.environ["WALNUT_ALLOWED_ORIGINS"] = "http://test.com"
    os.environ["WALNUT_SIGNUP_ENABLED"] = "true"

    # Initialize the database with the test DB path
    init_db(test_db)

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

