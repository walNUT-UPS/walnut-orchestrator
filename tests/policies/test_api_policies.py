import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_list_policies(async_client: AsyncClient):
    response = await async_client.get("/api/policies")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

async def test_create_policy(async_client: AsyncClient):
    policy_data = {
        "name": "New Test Policy",
        "priority": 200,
        "trigger": {"type": "status_transition", "from": "OL", "to": "OB"},
        "targets": {"selector": {"hosts": ["host1"]}},
        "safeties": {},
        "steps": [{"type": "notify"}],
    }
    response = await async_client.post("/api/policies", json=policy_data)
    assert response.status_code == 201
    response_data = response.json()
    assert response_data["name"] == "New Test Policy"
    assert "id" in response_data

async def test_create_invalid_policy(async_client: AsyncClient):
    policy_data = {"name": "Invalid Policy"} # Missing required fields
    response = await async_client.post("/api/policies", json=policy_data)
    assert response.status_code == 422 # Unprocessable Entity

async def test_get_policy(async_client: AsyncClient):
    # First create a policy
    policy_data = {
        "name": "Gettable Policy",
        "priority": 100,
        "trigger": {"type": "status_transition", "from": "OL", "to": "OB"},
        "targets": {"selector": {"hosts": ["host1"]}},
        "safeties": {},
        "steps": [{"type": "notify"}],
    }
    create_response = await async_client.post("/api/policies", json=policy_data)
    policy_id = create_response.json()["id"]

    # Then get it
    response = await async_client.get(f"/api/policies/{policy_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Gettable Policy"

async def test_reorder_policies(async_client: AsyncClient):
    reorder_data = [
        {"id": 1, "order": 1},
        {"id": 2, "order": 0},
    ]
    response = await async_client.post("/api/policies/reorder", json=reorder_data)
    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, list)
    # Check that the priorities are recomputed correctly
    assert {"id": 2, "priority": 255} in response_data
    assert {"id": 1, "priority": 254} in response_data
