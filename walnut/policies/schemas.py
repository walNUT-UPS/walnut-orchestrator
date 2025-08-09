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
    hosts: List[str] = []
    tags: List[str] = []
    types: List[str] = []

class Targets(BaseModel):
    selector: TargetSelector

class Safeties(BaseModel):
    suppression_window: Optional[str] = None
    global_lock: Optional[str] = None
    never_hosts: List[str] = []

class Step(BaseModel):
    type: Literal["ssh.shutdown", "proxmox.suspend", "webhook.post", "notify", "sleep"]
    params: Dict[str, Any] = {}
    timeout: Optional[str] = "120s"
    retries: Optional[int] = 0
    backoff: Optional[str] = "10s"
    continue_on_error: Optional[bool] = False

class PolicySchema(BaseModel):
    version: str = "1.0"
    name: str
    enabled: bool = True
    priority: int = Field(ge=0, le=255)
    trigger: Trigger
    conditions: Conditions
    targets: Targets
    safeties: Safeties
    steps: List[Step]

# Models for compiled plan
class CompiledStep(BaseModel):
    step_no: int
    type: str
    params: Dict[str, Any]
    target: str
    timeout: int # in seconds
    retries: int
    backoff: int # in seconds
    continue_on_error: bool

class CompiledPlan(BaseModel):
    policy_name: str
    policy_id: Optional[int] = None
    event: Optional[Dict[str, Any]] = None
    targets: List[str]
    steps: List[CompiledStep]
    would_be_suppressed: bool = False
