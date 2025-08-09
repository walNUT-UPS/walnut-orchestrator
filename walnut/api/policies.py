from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional

from walnut.policies.schemas import PolicySchema
from walnut.policies.linter import lint_policy
from walnut.policies.plan import compile_plan
from walnut.policies.priority import recompute_priorities

router = APIRouter()

# Placeholder for in-memory storage, since we are not using the DB yet
policies_db = {}
next_policy_id = 1

@router.get("/policies", summary="List all policies")
async def list_policies(enabled: Optional[bool] = None):
    # In a real implementation, this would query the database.
    # For now, return a placeholder list.
    return [
        {"id": 1, "name": "Policy 1", "enabled": True, "priority": 255, "last_run_status": "success"},
        {"id": 2, "name": "Policy 2", "enabled": False, "priority": 128, "last_run_status": "failed"},
    ]

@router.post("/policies", summary="Create a new policy", status_code=201)
async def create_policy(policy: PolicySchema):
    global next_policy_id
    lint_result = lint_policy(policy)
    if lint_result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": lint_result["errors"]})

    new_id = next_policy_id
    policies_db[new_id] = policy.dict()
    next_policy_id += 1

    return {"id": new_id, **policy.dict(), "warnings": lint_result["warnings"]}

@router.get("/policies/{policy_id}", summary="Get a single policy")
async def get_policy(policy_id: int):
    if policy_id not in policies_db:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policies_db[policy_id]

@router.put("/policies/{policy_id}", summary="Update a policy")
async def update_policy(policy_id: int, policy: PolicySchema):
    if policy_id not in policies_db:
        raise HTTPException(status_code=404, detail="Policy not found")

    lint_result = lint_policy(policy)
    if lint_result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": lint_result["errors"]})

    policies_db[policy_id] = policy.dict()
    return {"id": policy_id, **policy.dict(), "warnings": lint_result["warnings"]}

@router.delete("/policies/{policy_id}", summary="Delete a policy", status_code=204)
async def delete_policy(policy_id: int):
    if policy_id not in policies_db:
        raise HTTPException(status_code=404, detail="Policy not found")
    del policies_db[policy_id]
    return

@router.post("/policies/reorder", summary="Reorder policies")
async def reorder_policies(ordered_policies: List[Dict[str, Any]]):
    # In a real implementation, this would update the priorities in the DB.
    # For now, we just recompute and return them.
    new_priorities = recompute_priorities(ordered_policies)
    return new_priorities

@router.post("/policies/{policy_id}/lint", summary="Lint a policy")
async def lint_policy_endpoint(policy_id: int):
    if policy_id not in policies_db:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy = PolicySchema(**policies_db[policy_id])
    return lint_policy(policy)

@router.post("/policies/{policy_id}/plan", summary="Generate a plan for a policy")
async def plan_policy(policy_id: int, event: Optional[Dict[str, Any]] = None):
    if policy_id not in policies_db:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy = PolicySchema(**policies_db[policy_id])
    plan = compile_plan(policy, event, policy_id)
    return plan.dict()
