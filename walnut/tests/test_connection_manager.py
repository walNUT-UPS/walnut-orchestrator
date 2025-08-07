import pytest
import asyncio
from walnut.database.connection import ConnectionManager

@pytest.mark.asyncio
async def test_connection_manager_startup_shutdown():
    # Use a test config or mock if available, else just instantiate
    cm = ConnectionManager()
    result = await cm.startup()
    assert isinstance(result, dict)
    await cm.shutdown()
