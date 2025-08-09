from fastapi import APIRouter, HTTPException
from typing import List, Optional

router = APIRouter()

# Placeholder for in-memory storage
policy_runs_db = {
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
async def list_policy_runs(policy_id: Optional[int] = None, limit: int = 20):
    # In a real implementation, this would query the database.
    # For now, return a placeholder list.
    if policy_id:
        return [run for run in policy_runs_db.values() if run["policy_id"] == policy_id]
    return list(policy_runs_db.values())

@router.get("/policy-runs/{run_id}", summary="Get a single policy run")
async def get_policy_run(run_id: int):
    if run_id not in policy_runs_db:
        raise HTTPException(status_code=404, detail="Policy run not found")
    return policy_runs_db[run_id]
