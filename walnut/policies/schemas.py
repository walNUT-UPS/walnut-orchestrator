from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any, Optional

class Trigger(BaseModel):
    type: Literal["status_transition", "duration", "schedule"]
    from_status: Optional[str] = Field(alias="from", default=None)
    to_status: Optional[str] = Field(alias="to", default=None)
    stable_for: Optional[str] = None

class Conditions(BaseModel):
    all: List[Dict[str, Any]] = []
    any: List[Dict[str, Any]] = []

class TargetSelector(BaseModel):
    """Defines the selector for finding targets for an action."""
    labels: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Select targets by labels, e.g., {'tier': 'critical'}")
    attrs: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Select targets by attributes, e.g., {'os': 'linux'}")
    names: Optional[List[str]] = Field(default_factory=list, description="Select targets by their display name")
    external_ids: Optional[List[str]] = Field(default_factory=list, description="Select targets by their external ID from the integration")


class CapabilityAction(BaseModel):
    """Defines a capability-based action to be performed."""
    capability: str = Field(..., description="The capability to invoke, e.g., 'vm.lifecycle'")
    verb: str = Field(..., description="The specific action to perform, e.g., 'shutdown'")
    selector: TargetSelector = Field(default_factory=TargetSelector, description="Selector for the targets of this action")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Options for the action, e.g., {'timeout': 60}")


class Safeties(BaseModel):
    suppression_window: Optional[str] = None
    global_lock: Optional[str] = None
    never_hosts: List[str] = [] # This might need to be re-evaluated with the new target model


class PolicySchema(BaseModel):
    version: str = "2.0" # Bump version for new schema
    name: str
    enabled: bool = True
    priority: int = Field(ge=0, le=255)
    trigger: Trigger
    conditions: Conditions
    safeties: Safeties
    actions: List[CapabilityAction]
