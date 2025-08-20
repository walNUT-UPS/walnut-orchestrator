"""
API endpoints for managing shutdown and automation policies.

This module provides a full set of CRUD (Create, Read, Update, Delete)
endpoints for managing policies. It also includes endpoints for linting
and reordering policies.

NOTE: This implementation uses an in-memory dictionary as a placeholder
for a real database. It is intended for demonstration and testing purposes.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional

from walnut.auth.deps import current_active_user
from walnut.auth.models import User
from walnut.policies.schemas import PolicySchema
from walnut.policies.linter import lint_policy
from walnut.policies.priority import recompute_priorities

router = APIRouter()

# Placeholder for in-memory storage. In a real application, this would
# be replaced with database models and queries.
policies_db: Dict[int, Dict[str, Any]] = {}
next_policy_id = 1

@router.get("/policies", summary="List all policies", response_model=List[Dict[str, Any]])
async def list_policies(
    enabled: Optional[bool] = None,
    user: User = Depends(current_active_user),
):
    """
    Retrieve a list of all policies.

    Optionally filters policies by their 'enabled' status.
    """
    # In a real implementation, this would query the database.
    # For now, return a placeholder list.
    policies = [
        {"id": 1, "name": "Policy 1", "enabled": True, "priority": 255, "last_run_status": "success"},
        {"id": 2, "name": "Policy 2", "enabled": False, "priority": 128, "last_run_status": "failed"},
    ]
    if enabled is not None:
        return [p for p in policies if p["enabled"] == enabled]
    return policies

@router.post(
    "/policies",
    summary="Create a new policy",
    status_code=201,
    response_model=Dict[str, Any],
    responses={
        422: {"description": "Validation error if the policy has linting errors."}
    },
)
async def create_policy(
    policy: PolicySchema,
    user: User = Depends(current_active_user),
):
    """
    Create a new policy.

    The policy is first validated by the linter. If there are errors,
    the creation will fail with a 422 error. Warnings are returned
    in the response but do not block creation.
    """
    global next_policy_id
    lint_result = lint_policy(policy)
    if lint_result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": lint_result["errors"]})

    new_id = next_policy_id
    policies_db[new_id] = policy.model_dump()
    next_policy_id += 1

    return {"id": new_id, **policy.model_dump(), "warnings": lint_result["warnings"]}

@router.get(
    "/policies/{policy_id}",
    summary="Get a single policy",
    response_model=Dict[str, Any],
    responses={404: {"description": "Policy not found."}},
)
async def get_policy(
    policy_id: int,
    user: User = Depends(current_active_user),
):
    """Retrieve a single policy by its ID."""
    if policy_id not in policies_db:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policies_db[policy_id]

@router.put(
    "/policies/{policy_id}",
    summary="Update a policy",
    response_model=Dict[str, Any],
    responses={
        404: {"description": "Policy not found."},
        422: {"description": "Validation error if the policy has linting errors."}
    },
)
async def update_policy(
    policy_id: int,
    policy: PolicySchema,
    user: User = Depends(current_active_user),
):
    """
    Update an existing policy.

    The updated policy is validated by the linter before saving.
    """
    if policy_id not in policies_db:
        raise HTTPException(status_code=404, detail="Policy not found")

    lint_result = lint_policy(policy)
    if lint_result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": lint_result["errors"]})

    policies_db[policy_id] = policy.model_dump()
    return {"id": policy_id, **policy.model_dump(), "warnings": lint_result["warnings"]}

@router.delete(
    "/policies/{policy_id}",
    summary="Delete a policy",
    status_code=204,
    responses={404: {"description": "Policy not found."}},
)
async def delete_policy(
    policy_id: int,
    user: User = Depends(current_active_user),
):
    """Delete a policy by its ID."""
    if policy_id not in policies_db:
        raise HTTPException(status_code=404, detail="Policy not found")
    del policies_db[policy_id]
    return

@router.post("/policies/reorder", summary="Reorder policies", response_model=List[Dict[str, Any]])
async def reorder_policies(
    ordered_policies: List[Dict[str, Any]],
    user: User = Depends(current_active_user),
):
    """
    Recalculate the priority of policies based on a new user-defined order.

    Accepts a list of policies in their desired order and returns the
    list with updated `priority` values.
    """
    # In a real implementation, this would update the priorities in the DB.
    # For now, we just recompute and return them.
    new_priorities = recompute_priorities(ordered_policies)
    return new_priorities

@router.post(
    "/policies/{policy_id}/lint",
    summary="Lint a policy",
    response_model=Dict[str, List[str]],
    responses={404: {"description": "Policy not found."}},
)
async def lint_policy_endpoint(
    policy_id: int,
    user: User = Depends(current_active_user),
):
    """
    Validate a policy's syntax and logic without saving it.

    Returns a dictionary with 'errors' and 'warnings'.
    """
    if policy_id not in policies_db:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy = PolicySchema(**policies_db[policy_id])
    return lint_policy(policy)
