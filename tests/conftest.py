import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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

@pytest.fixture
def cli_runner():
    return CliRunner()
