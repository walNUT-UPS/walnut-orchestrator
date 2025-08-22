"""
API endpoints for managing shutdown and automation policies.

Provides CRUD endpoints backed by the SQLCipher database and validation
helpers using the policy linter. Also exposes endpoints for policy
validation and a basic dry-run planner.

Policy System v1 endpoints are available when POLICY_V1_ENABLED=true.
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Dict, Any, Optional
import anyio
from sqlalchemy import select, desc
from uuid import uuid4
import logging

from walnut.auth.deps import current_active_user, require_current_user
from walnut.auth.models import User
from walnut.database.connection import get_db_session, get_db_session_dependency
from walnut.database.models import Policy as PolicyModel, PolicyV1, PolicyExecution, serialize_model
from walnut.policies.schemas import PolicySchema
from walnut.policies.linter import lint_policy
from walnut.policies.priority import recompute_priorities
from walnut.config import settings

# Policy System v1 imports (when enabled)
if settings.POLICY_V1_ENABLED:
    from walnut.policy import (
        PolicySpec, ValidationResult, PolicyDryRunResult, 
        validate_policy_spec, compile_policy
    )
    from walnut.policy.engine import create_policy_engine
    from walnut.inventory import create_inventory_index

router = APIRouter()

@router.get("/policies", summary="List all policies", response_model=List[Dict[str, Any]])
async def list_policies(
    enabled: Optional[bool] = None,
    user: User = Depends(require_current_user),
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
        rows = result.unique().scalars().all()
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
    user: User = Depends(require_current_user),
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
    user: User = Depends(require_current_user),
):
    """Retrieve a single policy by its ID."""
    async with get_db_session() as session:
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        row = result.unique().scalar_one_or_none()
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
    user: User = Depends(require_current_user),
    session=Depends(get_db_session_dependency)
):
    """
    Update an existing policy.

    The updated policy is validated by the linter before saving.
    """
    stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
    result = session.execute(stmt)
    row = result.unique().scalar_one_or_none()
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
        row = result.unique().scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found")
        await anyio.to_thread.run_sync(session.delete, row)
        await anyio.to_thread.run_sync(session.commit)
        return

@router.post("/policies/reorder", summary="Reorder policies", response_model=List[Dict[str, Any]])
async def reorder_policies(
    ordered_policies: List[Dict[str, Any]],
    user: User = Depends(require_current_user),
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
    user: User = Depends(require_current_user),
):
    """
    Validate a policy's syntax and logic without saving it.

    Returns a dictionary with 'errors' and 'warnings'.
    """
    async with get_db_session() as session:
        stmt = select(PolicyModel).where(PolicyModel.id == policy_id)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        row = result.unique().scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found")
        policy = PolicySchema(**row.json)
        return lint_policy(policy)

@router.post("/policies/validate", summary="Validate a policy spec", response_model=Dict[str, List[str]])
async def validate_policy_spec(payload: PolicySchema, user: User = Depends(require_current_user)):
    return lint_policy(payload)

@router.post("/policies/test", summary="Dry-run a policy", response_model=Dict[str, Any])
async def test_policy_dry_run(payload: PolicySchema, user: User = Depends(require_current_user)):
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


# ===== Policy System v1 Endpoints =====

def _check_policy_v1_enabled():
    """Raise 501 if Policy System v1 is not enabled."""
    if not settings.POLICY_V1_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Policy System v1 is not enabled. Set WALNUT_POLICY_V1_ENABLED=true to enable."
        )


@router.post("/v1/validate", summary="Validate Policy v1 spec", response_model=Dict[str, Any])
async def validate_policy_v1(
    spec: Dict[str, Any],
    user: User = Depends(require_current_user),
):
    """
    Validate policy specification and compile to IR.
    
    Returns validation result with schema/compile errors and compiled IR.
    """
    _check_policy_v1_enabled()
    
    try:
        result = validate_policy_spec(spec)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Validation failed: {str(e)}")


@router.post("/v1/policies", summary="Create Policy v1", response_model=Dict[str, Any])
async def create_policy_v1(
    spec: Dict[str, Any],
    user: User = Depends(require_current_user),
):
    """
    Create new policy from specification.
    
    Validates spec, compiles to IR, and saves to database.
    Returns 409 if identical hash exists, 400 on compilation errors.
    """
    _check_policy_v1_enabled()
    
    try:
        # Validate and compile
        result = compile_policy(spec)
        
        if not result.ok:
            # Check for blockers
            blockers = [err for err in (result.schema + result.compile) if err.path]
            if blockers:
                raise HTTPException(status_code=400, detail={
                    "message": "Policy has blocking errors",
                    "errors": [{"path": err.path, "message": err.message} for err in blockers]
                })
        
        # Check for duplicate hash
        async with get_db_session() as session:
            existing_stmt = select(PolicyV1).where(PolicyV1.hash == result.hash)
            existing_result = await anyio.to_thread.run_sync(session.execute, existing_stmt)
            existing_policy = existing_result.scalar_one_or_none()
            
            if existing_policy:
                raise HTTPException(status_code=409, detail={
                    "message": "Policy with identical specification already exists",
                    "existing_policy_id": existing_policy.id
                })
            
            # Create new policy
            policy_id = str(uuid4())
            policy_status = "enabled" if result.ok else "disabled"
            
            new_policy = PolicyV1(
                id=policy_id,
                name=spec.get("name", "Untitled Policy"),
                status=policy_status,
                version_int=1,
                hash=result.hash,
                priority=spec.get("priority", 0),
                stop_on_match=spec.get("stop_on_match", False),
                dynamic_resolution=spec.get("dynamic_resolution", True),
                suppression_window_s=300,  # Default 5 minutes
                idempotency_window_s=600,  # Default 10 minutes
                spec=spec,
                compiled_ir=result.ir.model_dump() if result.ir else None,
                last_validation={"ts": anyio.current_time(), "errors": len(result.schema + result.compile)}
            )
            
            session.add(new_policy)
            await anyio.to_thread.run_sync(session.commit)
            
            return {
                "policy_id": policy_id,
                "status": policy_status,
                "validation": result.model_dump()
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create policy: {str(e)}")


@router.put("/v1/policies/{policy_id}", summary="Update Policy v1", response_model=Dict[str, Any])
async def update_policy_v1(
    policy_id: str,
    spec: Dict[str, Any],
    user: User = Depends(require_current_user),
):
    """
    Update existing policy specification.
    
    Bumps version_int, re-compiles, and updates hash.
    """
    _check_policy_v1_enabled()
    
    async with get_db_session() as session:
        # Get existing policy
        stmt = select(PolicyV1).where(PolicyV1.id == policy_id)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        policy = result.scalar_one_or_none()
        
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        try:
            # Validate and compile new spec
            validation_result = compile_policy(spec)
            
            # Update policy
            policy.name = spec.get("name", policy.name)
            policy.version_int += 1
            policy.hash = validation_result.hash
            policy.priority = spec.get("priority", policy.priority)
            policy.stop_on_match = spec.get("stop_on_match", policy.stop_on_match)
            policy.dynamic_resolution = spec.get("dynamic_resolution", policy.dynamic_resolution)
            policy.spec = spec
            policy.compiled_ir = validation_result.ir.model_dump() if validation_result.ir else None
            policy.last_validation = {
                "ts": anyio.current_time(), 
                "errors": len(validation_result.schema + validation_result.compile)
            }
            policy.status = "enabled" if validation_result.ok else "disabled"
            
            await anyio.to_thread.run_sync(session.commit)
            
            return {
                "policy_id": policy_id,
                "version_int": policy.version_int,
                "status": policy.status,
                "validation": validation_result.model_dump()
            }
            
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Update failed: {str(e)}")


@router.post("/v1/policies/{policy_id}/dry-run", summary="Policy v1 dry-run", response_model=Dict[str, Any])
async def dry_run_policy_v1(
    policy_id: str,
    refresh: bool = True,
    user: User = Depends(require_current_user),
):
    """
    Perform dry-run of policy against current system state.
    
    Refreshes inventory (fast SLA), calls drivers with dry_run=True,
    and returns detailed transcript.
    """
    _check_policy_v1_enabled()
    
    async with get_db_session() as session:
        # Get policy
        stmt = select(PolicyV1).where(PolicyV1.id == policy_id)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        policy = result.scalar_one_or_none()
        
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        if not policy.compiled_ir:
            raise HTTPException(status_code=400, detail="Policy has no compiled IR")
        
        try:
            # Create policy engine and inventory index (placeholder)
            policy_engine = create_policy_engine()
            
            # Parse policy IR
            from walnut.policy.models import PolicyIR
            policy_ir = PolicyIR.model_validate(policy.compiled_ir)
            
            # Perform dry-run
            dry_run_result = await policy_engine.dry_run_policy(policy_ir, refresh_inventory=refresh)
            
            # Update policy with dry-run result
            policy.last_dry_run = {
                "ts": anyio.current_time(),
                "severity": dry_run_result.severity.value,
                "transcript_id": str(dry_run_result.transcript_id)
            }
            await anyio.to_thread.run_sync(session.commit)
            
            return dry_run_result.model_dump()
            
        except Exception as e:
            logging.exception(f"Dry-run failed for policy {policy_id}")
            raise HTTPException(status_code=500, detail=f"Dry-run failed: {str(e)}")


@router.get("/v1/policies/{policy_id}/executions", summary="Policy v1 execution history", response_model=List[Dict[str, Any]])
async def get_policy_executions_v1(
    policy_id: str,
    limit: int = 30,
    user: User = Depends(require_current_user),
):
    """
    Get most recent execution summaries for policy.
    
    Returns last N executions ordered by timestamp descending.
    """
    _check_policy_v1_enabled()
    
    async with get_db_session() as session:
        # Verify policy exists
        policy_stmt = select(PolicyV1).where(PolicyV1.id == policy_id)
        policy_result = await anyio.to_thread.run_sync(session.execute, policy_stmt)
        policy = policy_result.scalar_one_or_none()
        
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        # Get executions
        executions_stmt = (
            select(PolicyExecution)
            .where(PolicyExecution.policy_id == policy_id)
            .order_by(desc(PolicyExecution.ts))
            .limit(limit)
        )
        
        executions_result = await anyio.to_thread.run_sync(session.execute, executions_stmt)
        executions = executions_result.scalars().all()
        
        return [serialize_model(execution) for execution in executions]


@router.post("/v1/policies/{policy_id}/inverse", summary="Create inverse policy v1", response_model=Dict[str, Any])
async def create_inverse_policy_v1(
    policy_id: str,
    user: User = Depends(require_current_user),
):
    """
    Compute inverse policy per capability/trigger inverse registry.
    
    Returns unsaved spec with needs_input list for user completion.
    """
    _check_policy_v1_enabled()
    
    async with get_db_session() as session:
        # Get policy
        stmt = select(PolicyV1).where(PolicyV1.id == policy_id)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        policy = result.scalar_one_or_none()
        
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")
        
        try:
            # Create inverse spec (simplified logic)
            original_spec = policy.spec
            inverse_spec = original_spec.copy()
            
            # Flip actions based on invertible mappings (would need actual capability resolution)
            inverse_spec["name"] = f"Inverse of {original_spec.get('name', 'Untitled')}"
            inverse_spec["enabled"] = False
            
            # Mark fields that need user input
            needs_input = []
            
            # Timer triggers need user input for schedules
            trigger_group = inverse_spec.get("trigger_group", {})
            for i, trigger in enumerate(trigger_group.get("triggers", [])):
                if trigger.get("type", "").startswith("timer"):
                    needs_input.append(f"trigger_group.triggers[{i}].schedule.at")
            
            return {
                "spec_inverse": inverse_spec,
                "enabled": False,
                "needs_input": needs_input,
                "notes": f"Inverse of policy {policy_id[:8]}..."
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create inverse: {str(e)}")


# ===== Host Helper Endpoints =====

@router.get("/v1/hosts/{host_id}/capabilities", summary="Get host capabilities", response_model=Dict[str, Any])
async def get_host_capabilities_v1(
    host_id: str,
    user: User = Depends(require_current_user),
):
    """
    Get capabilities available for a host.
    
    Returns capabilities from integration metadata for policy target selection.
    """
    _check_policy_v1_enabled()
    
    try:
        # Create inventory index (would be injected in production)
        inventory_index = create_inventory_index()
        
        # Get host capabilities
        from uuid import UUID
        capabilities = await inventory_index.get_host_capabilities(UUID(host_id))
        
        return capabilities.model_dump()
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get capabilities: {str(e)}")


@router.get("/v1/hosts/{host_id}/inventory", summary="Get host inventory", response_model=Dict[str, Any])
async def get_host_inventory_v1(
    host_id: str,
    refresh: bool = False,
    user: User = Depends(require_current_user),
):
    """
    Get host inventory with discovered targets.
    
    Optionally refreshes inventory from integration discovery.
    Returns targets with canonical IDs, names, and searchable labels.
    """
    _check_policy_v1_enabled()
    
    try:
        # Create inventory index (would be injected in production)
        inventory_index = create_inventory_index()
        
        # Get host inventory
        from uuid import UUID
        inventory = await inventory_index.get_host_inventory(UUID(host_id), refresh=refresh)
        
        return inventory.model_dump()
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get inventory: {str(e)}")
