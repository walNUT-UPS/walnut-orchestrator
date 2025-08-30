import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import os
import tempfile
from pathlib import Path
from httpx import AsyncClient

# Skip integration tests unless explicitly enabled
def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", default=False, help="Run integration tests")

def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(reason="need --integration option to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)
from walnut.app import app
from walnut.database.engine import init_db
from alembic.config import Config
from alembic import command
import respx



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
        # Create empty DB file; schema will be ensured by tests
        db_path.touch()
        yield str(db_path)
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

    # Initialize the database with the test DB path and ensure schema
    init_db(test_db)
    from walnut.database.engine import ensure_schema
    ensure_schema()

    # Override auth dependencies to bypass real JWT/cookies in tests
    from types import SimpleNamespace
    from walnut.auth.deps import require_current_user, current_active_user
    from walnut.auth.models import Role
    test_user = SimpleNamespace(id="test-user", email="test@example.com", is_active=True, is_verified=True, role=Role.ADMIN)
    app.dependency_overrides[require_current_user] = lambda: test_user
    app.dependency_overrides[current_active_user] = lambda: test_user

    import httpx
    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"Authorization": "Bearer test-token"}) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
@respx.mock
async def oidc_async_client(test_db):
    """
    A fixture that provides an httpx.AsyncClient for testing OIDC functionality.
    """
    # Mock the OIDC discovery endpoint
    OIDC_PROVIDER_URL = "https://example.com"
    respx.get(f"{OIDC_PROVIDER_URL}/.well-known/openid-configuration").mock(
        return_value=respx.Response(200, json={
            "authorization_endpoint": f"{OIDC_PROVIDER_URL}/auth",
            "token_endpoint": f"{OIDC_PROVIDER_URL}/token",
            "userinfo_endpoint": f"{OIDC_PROVIDER_URL}/userinfo",
        })
    )
    
    # Set OIDC environment variables
    os.environ["WALNUT_OIDC_ENABLED"] = "true"
    os.environ["WALNUT_OIDC_CLIENT_ID"] = "test_client_id"
    os.environ["WALNUT_OIDC_CLIENT_SECRET"] = "test_client_secret"
    os.environ["WALNUT_OIDC_DISCOVERY_URL"] = f"{OIDC_PROVIDER_URL}/.well-known/openid-configuration"
    os.environ["WALNUT_OIDC_ADMIN_ROLES"] = '["admin"]'
    os.environ["WALNUT_OIDC_VIEWER_ROLES"] = '["viewer"]'

    # Standard test environment
    os.environ["WALNUT_TESTING"] = "true"
    os.environ["WALNUT_DB_PATH"] = test_db
    os.environ["WALNUT_ALLOWED_ORIGINS"] = "http://test.com"
    os.environ["WALNUT_SIGNUP_ENABLED"] = "true"
    os.environ["WALNUT_DB_KEY"] = "a-test-key-that-is-long-enough-for-sqlcipher"
    os.environ["WALNUT_JWT_SECRET"] = "test-secret"

    # Initialize the database with the test DB path
    init_db(test_db)

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
