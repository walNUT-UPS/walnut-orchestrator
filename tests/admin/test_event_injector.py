import pytest
from httpx import AsyncClient
from walnut.app import app
from walnut.api.admin_events import get_current_admin_user
from tests.conftest import get_current_admin_user_override

pytestmark = pytest.mark.asyncio

async def test_inject_event(async_client: AsyncClient):
    app.dependency_overrides[get_current_admin_user] = get_current_admin_user_override
    event_data = {
        "source": "sim",
        "type": "nut.status",
        "from": "OL",
        "to": "OB",
    }
    response = await async_client.post("/api/admin/events/inject", json=event_data)
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["source"] == "sim"
    assert response_data["type"] == "nut.status"
    assert "id" in response_data
    assert "occurred_at" in response_data

    # Clean up the override
    app.dependency_overrides = {}
