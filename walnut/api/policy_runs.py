"""
API endpoints for viewing the results of policy executions.

This module provides endpoints to list and retrieve the details
of policy runs, including their status and timeline of actions.

NOTE: This implementation uses an in-memory dictionary as a placeholder
for a real database.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from walnut.auth.csrf import csrf_protect
from typing import List, Optional, Dict, Any

from walnut.auth.deps import current_active_user
from walnut.auth.models import User


router = APIRouter(dependencies=[Depends(csrf_protect)])

# Placeholder for in-memory storage
policy_runs_db: Dict[int, Dict[str, Any]] = {
    1: {
        "id": 1,
        "policy_id": 1,
        "status": "dry_run",
        "started_at": "2023-10-27T10:00:00Z",
        "finished_at": "2023-10-27T10:00:15Z",
        "timeline": [
            {"step": 1, "action": "notify", "status": "success", "duration": "1s"},
            {"step": 2, "action": "sleep", "status": "success", "duration": "10s"},
            {"step": 3, "action": "ssh.shutdown", "status": "success", "duration": "3s"},
        ]
    }
}

@router.get("/policy-runs", summary="List policy runs")
async def list_policy_runs(
    policy_id: Optional[int] = Query(None, description="Filter runs by a specific policy ID."),
    limit: int = Query(20, ge=1, le=100, description="The maximum number of runs to return."),
    user: User = Depends(current_active_user),
):
    """
    Retrieve a list of policy runs.

    Can be filtered by policy ID to see the history for a specific policy.
    """
    # In a real implementation, this would query the database.
    # For now, return a placeholder list.
    if policy_id:
        runs = [run for run in policy_runs_db.values() if run["policy_id"] == policy_id]
    else:
        runs = list(policy_runs_db.values())
    return runs[:limit]

@router.get(
    "/policy-runs/{run_id}",
    summary="Get a single policy run",
    responses={404: {"description": "Policy run not found."}},
)
async def get_policy_run(
    run_id: int,
    user: User = Depends(current_active_user),
):
    """
    Retrieve the details of a single policy run by its ID.

    This includes the full timeline of actions taken during the run.
    """
    if run_id not in policy_runs_db:
        raise HTTPException(status_code=404, detail="Policy run not found")
    return policy_runs_db[run_id]
