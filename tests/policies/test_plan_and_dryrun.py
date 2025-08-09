import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_generate_plan(async_client: AsyncClient):
    # First create a policy
    policy_data = {
        "name": "Plannable Policy",
        "priority": 100,
        "trigger": {"type": "status_transition", "from": "OL", "to": "OB"},
        "targets": {"selector": {"hosts": ["host1", "host2"]}},
        "safeties": {},
        "steps": [{"type": "notify"}, {"type": "sleep", "params": {"duration": "5s"}}],
    }
    create_response = await async_client.post("/api/policies", json=policy_data)
    assert create_response.status_code == 201
    policy_id = create_response.json()["id"]

    # Then generate a plan for it
    response = await async_client.post(f"/api/policies/{policy_id}/plan")
    assert response.status_code == 200
    plan = response.json()
    assert plan["policy_name"] == "Plannable Policy"
    assert len(plan["targets"]) == 2
    assert len(plan["steps"]) == 4 # 2 steps * 2 targets
    assert plan["steps"][0]["target"] == "host1.example.com"
    assert plan["steps"][1]["target"] == "host1.example.com"
    assert plan["steps"][2]["target"] == "host2.example.com"

@pytest.mark.skip(reason="Dry-run functionality not implemented yet")
async def test_dry_run(async_client: AsyncClient):
    # This test will be implemented in P2
    pass
