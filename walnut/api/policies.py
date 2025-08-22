"""
API endpoints for managing shutdown and automation policies.

Provides CRUD endpoints backed by the SQLCipher database and validation
helpers using the policy linter. Also exposes endpoints for policy
validation and a basic dry-run planner.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
import anyio
from sqlalchemy import select

from walnut.auth.deps import current_active_user
from walnut.auth.models import User
from walnut.database.connection import get_db_session, get_db_session_dependency
from walnut.database.models import Policy as PolicyModel, serialize_model
from walnut.policies.schemas import PolicySchema
from walnut.policies.linter import lint_policy
from walnut.policies.priority import recompute_priorities

router = APIRouter()

@router.get("/policies", summary="List all policies", response_model=List[Dict[str, Any]])
async def list_policies(
    enabled: Optional[bool] = None,
    user: User = Depends(current_active_user),
):
    """
    Retrieve a list of all policies.

    Optionally filters policies by their 'enabled' status.
    """
    async with get_db_session() as session:
        stmt = select(PolicyModel)
        if enabled is not None:
            stmt = stmt.where(PolicyModel.enabled == enabled)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        rows = result.scalars().all()
        return [
            {
                **serialize_model(row),
                # Expose convenient fields commonly shown in UI
                "name": row.name,
                "enabled": row.enabled,
                "priority": row.priority,
                "json": row.json,
            }
            for row in rows
        ]

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
    session=Depends(get_db_session_dependency)
):
    """
    Create a new policy.

    The policy is first validated by the linter. If there are errors,
    the creation will fail with a 422 error. Warnings are returned
    in the response but do not block creation.
    """
    lint_result = lint_policy(policy)
    if lint_result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": lint_result["errors"]})

    model = PolicyModel(
        name=policy.name,
        enabled=policy.enabled,
        priority=policy.priority,
        json=policy.model_dump(mode="json"),
    )
    session.add(model)
    await anyio.to_thread.run_sync(session.flush)
    await anyio.to_thread.run_sync(session.refresh, model)
    return {"id": model.id, **serialize_model(model), "warnings": lint_result["warnings"]}

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
    async with get_db_session() as session:
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found")
        return serialize_model(row)

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
    session=Depends(get_db_session_dependency)
):
    """
    Update an existing policy.

    The updated policy is validated by the linter before saving.
    """
    stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
    result = session.execute(stmt)
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")

    lint_result = lint_policy(policy)
    if lint_result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": lint_result["errors"]})

    row.name = policy.name
    row.enabled = policy.enabled
    row.priority = policy.priority
    row.json = policy.model_dump(mode="json")
    await anyio.to_thread.run_sync(session.flush)
    return {"id": row.id, **serialize_model(row), "warnings": lint_result["warnings"]}

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
    async with get_db_session() as session:
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found")
        await anyio.to_thread.run_sync(session.delete, row)
        await anyio.to_thread.run_sync(session.commit)
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
    # Recompute and return new priorities; caller can then persist if needed.
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
    async with get_db_session() as session:
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found")
        policy = PolicySchema(**row.json)
        return lint_policy(policy)

@router.post("/policies/validate", summary="Validate a policy spec", response_model=Dict[str, List[str]])
async def validate_policy_spec(payload: PolicySchema, user: User = Depends(current_active_user)):
    return lint_policy(payload)

@router.post("/policies/test", summary="Dry-run a policy", response_model=Dict[str, Any])
async def test_policy_dry_run(payload: PolicySchema, user: User = Depends(current_active_user)):
    """
    Produce a dry-run plan for the submitted policy. This does not mutate state
    or contact external systems; it assembles an execution plan from the policy
    actions and selectors.
    """
    plan = []
    for idx, action in enumerate(payload.actions):
        plan.append({
            "step": idx + 1,
            "capability": action.capability,
            "verb": action.verb,
            "selector": action.selector.model_dump(),
            "expected_targets": 0,  # Target resolution happens at execution time
            "options": action.options or {},
        })
    return {"status": "ok", "plan": plan}
