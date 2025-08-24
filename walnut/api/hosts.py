from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
import anyio
from sqlalchemy import select

from walnut.auth.deps import require_current_user
from walnut.auth.models import User
from walnut.database.connection import get_db_session
from walnut.database.models import IntegrationInstance, IntegrationType

router = APIRouter()


@router.get("/hosts", summary="List managed hosts", response_model=List[Dict[str, Any]])
async def list_hosts(_user: User = Depends(require_current_user)) -> List[Dict[str, Any]]:
    """
    Return hosts derived from integration instances (policy.md: Host is an instance).
    """
    async with get_db_session() as session:
        stmt = select(IntegrationInstance)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        rows = result.unique().scalars().all()
        return [
            {
                "id": str(row.instance_id),
                "name": row.name,
                "type_id": row.type_id,
                "ip_address": None,
                "os_type": None,
                "status": row.state,
            }
            for row in rows
        ]


@router.get("/hosts/{host_id}/capabilities", summary="Get host capabilities", response_model=List[Dict[str, Any]])
async def get_host_capabilities(host_id: str, _user: User = Depends(require_current_user)) -> List[Dict[str, Any]]:
    """
    Return available capabilities for a host by resolving its integration type.
    """
    async with get_db_session() as session:
        # Find instance and its type
        inst_stmt = select(IntegrationInstance).where(IntegrationInstance.instance_id == int(host_id))
        inst_res = await anyio.to_thread.run_sync(session.execute, inst_stmt)
        inst = inst_res.unique().scalar_one_or_none()
        if not inst:
            raise HTTPException(status_code=404, detail="Host not found")
        type_stmt = select(IntegrationType).where(IntegrationType.id == inst.type_id)
        type_res = await anyio.to_thread.run_sync(session.execute, type_stmt)
        t = type_res.unique().scalar_one_or_none()
        if not t:
            return []
        caps = t.capabilities or []
        # Normalize capability structure
        out: List[Dict[str, Any]] = []
        for c in caps:
            cid = c.get("id") if isinstance(c, dict) else None
            # Hide non-policy capabilities like inventory.list from editor
            if cid == "inventory.list":
                continue
            verbs = c.get("verbs") if isinstance(c, dict) else []
            invertible = c.get("invertible") if isinstance(c, dict) else {}
            targets = c.get("targets") if isinstance(c, dict) else []
            out.append({"id": cid, "verbs": verbs, "targets": targets, "invertible": invertible})
        return out


@router.get("/hosts/{host_id}/inventory", summary="Get host inventory")
async def get_host_inventory(host_id: str, refresh: bool = False, _user: User = Depends(require_current_user)) -> Dict[str, Any]:
    """
    Return discovered inventory for a host. Placeholder returns empty items list.
    """
    return {"items": []}
