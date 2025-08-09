from fastapi import APIRouter, Depends
from typing import Dict, Any, Optional
from datetime import datetime

router = APIRouter()

# A dummy dependency for admin role-guard
def get_current_admin_user():
    # In a real app, this would check the user's role from the token
    return {"username": "admin", "roles": ["admin"]}

@router.post("/admin/events/inject", summary="Inject a simulation event", dependencies=[Depends(get_current_admin_user)])
async def inject_event(event: Dict[str, Any]):
    # In a real implementation, this would write to the event_bus table.
    # For now, we just return the event with some defaults.
    injected_event = {
        "id": 123,
        "source": event.get("source", "sim"),
        "type": event.get("type", "nut.status"),
        "payload": {
            "from": event.get("from", "OL"),
            "to": event.get("to", "OB"),
            "duration": event.get("duration", "120s"),
            "meta": event.get("meta", {}),
        },
        "occurred_at": event.get("occurred_at", datetime.utcnow().isoformat()),
    }
    return injected_event
