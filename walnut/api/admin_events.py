"""
API endpoints for administrative actions, such as event simulation.

These endpoints are intended for testing and debugging purposes and
should be protected with administrator-level access in a production environment.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any, Optional
from datetime import datetime

from walnut.auth.models import User

router = APIRouter()

# A dummy dependency for admin role-guard. In a real application, this would
# be replaced with a proper RBAC (Role-Based Access Control) check.
def get_current_admin_user():
    """
    Dummy dependency to simulate an admin user check.

    In a real app, this would verify the user's roles from the JWT token.
    """
    # This is a placeholder. A real implementation would raise an HTTPException
    # if the user is not an admin.
    return {"username": "admin", "roles": ["admin"]}

@router.post(
    "/admin/events/inject",
    summary="Inject a simulation event",
    dependencies=[Depends(get_current_admin_user)],
    response_model=Dict[str, Any],
)
async def inject_event(event: Dict[str, Any]):
    """
    Inject a simulated event into the system.

    This is useful for testing how policies and integrations react to
    different types of events without needing a real hardware event.
    The event is not persisted; it is only returned in the response.

    Requires administrator privileges.
    """
    # In a real implementation, this would write to the event_bus table.
    # For now, we just return the event with some defaults.
    injected_event = {
        "id": 123,
        "source": event.get("source", "simulation"),
        "type": event.get("type", "nut.status.changed"),
        "payload": {
            "from": event.get("from", "OL"), # Online
            "to": event.get("to", "OB"),     # On Battery
            "duration": event.get("duration", "120s"),
            "meta": event.get("meta", {}),
        },
        "occurred_at": event.get("occurred_at", datetime.utcnow().isoformat()),
    }
    return injected_event
