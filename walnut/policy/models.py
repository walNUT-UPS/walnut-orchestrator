"""
Policy System Models (Pydantic Spec and IR models).

This module defines the Pydantic models for policy specifications,
intermediate representation (IR), and validation/execution results
as specified in POLICY.md v1.
"""

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class PolicyStatus(str, Enum):
    """Policy status enumeration."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    INVALID = "invalid"


class Severity(str, Enum):
    """Validation and execution severity levels."""
    INFO = "info"
    WARN = "warn"  
    ERROR = "error"
    BLOCKER = "blocker"


class TriggerLogic(str, Enum):
    """Trigger group logic operators."""
    ALL = "ALL"
    ANY = "ANY"


class SelectorMode(str, Enum):
    """Target selector mode."""
    LIST = "list"
    RANGE = "range" 
    QUERY = "query"


# ===== Policy Spec Models (User JSON) =====

class ScheduleSpec(BaseModel):
    """Timer schedule specification."""
    repeat: str = Field(description="Repeat pattern: daily, weekly, monthly")
    at: str = Field(description="Time in HH:MM format")
    days: Optional[List[str]] = Field(default=None, description="Days for weekly repeat")


class SinceEventSpec(BaseModel):
    """Event reference for timer.after triggers."""
    type: str = Field(description="Event type to reference")
    equals: str = Field(description="Event value to match")


class TriggerSpec(BaseModel):
    """Individual trigger specification."""
    type: str = Field(description="Trigger type: ups.state, metric.threshold, etc.")
    
    # Common fields
    equals: Optional[str] = Field(default=None, description="Exact match value")
    
    # Metric threshold fields
    metric: Optional[str] = Field(default=None, description="Metric name")
    op: Optional[str] = Field(default=None, description="Operator: >, >=, <, <=, =, !=")
    value: Optional[Union[int, float, str]] = Field(default=None, description="Threshold value")
    for_duration: Optional[str] = Field(default=None, description="Stability duration", alias="for")
    
    # Timer fields
    schedule: Optional[ScheduleSpec] = Field(default=None, description="Timer schedule")
    after: Optional[str] = Field(default=None, description="Duration after event")
    since_event: Optional[SinceEventSpec] = Field(default=None, description="Referenced event")


class TriggerGroupSpec(BaseModel):
    """Trigger group with logic operator."""
    logic: TriggerLogic = Field(default=TriggerLogic.ANY, description="Group logic: ALL or ANY")
    triggers: List[TriggerSpec] = Field(description="List of triggers")


class ConditionSpec(BaseModel):
    """Policy condition specification."""
    scope: str = Field(description="Condition scope: ups, host, metric, vm")
    field: str = Field(description="Field name to check")
    op: str = Field(description="Operator: >, >=, <, <=, =, !=")
    value: Union[int, float, str, bool] = Field(description="Comparison value")


class ConditionsSpec(BaseModel):
    """Policy conditions container."""
    all: List[ConditionSpec] = Field(description="AND conditions list")


class SelectorSpec(BaseModel):
    """Target selector specification."""
    mode: SelectorMode = Field(description="Selection mode")
    value: str = Field(description="Selector value (ranges, lists, queries)")


class TargetsSpec(BaseModel):
    """Policy targets specification."""
    host_id: UUID = Field(description="Target host UUID")
    target_type: str = Field(description="Target type: vm, poe-port, interface, etc.")
    selector: SelectorSpec = Field(description="Target selector")


class IdempotencySpec(BaseModel):
    """Idempotency configuration."""
    key_hint: Optional[str] = Field(default=None, description="Custom idempotency key hint")


class ActionSpec(BaseModel):
    """Policy action specification."""
    capability_id: str = Field(description="Driver capability ID")
    verb: str = Field(description="Action verb")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")
    idempotency: Optional[IdempotencySpec] = Field(default=None, description="Idempotency config")


class PolicySpec(BaseModel):
    """Complete policy specification (user JSON v1)."""
    version: Literal[1] = Field(default=1, description="Policy spec version")
    name: str = Field(min_length=3, description="Policy name")
    enabled: bool = Field(default=True, description="Policy enabled state")
    priority: int = Field(default=0, description="Execution priority (lower = higher priority)")
    stop_on_match: bool = Field(default=False, description="Stop processing on match")
    dynamic_resolution: bool = Field(default=True, description="Re-resolve targets at runtime")
    
    trigger_group: TriggerGroupSpec = Field(description="Trigger group")
    conditions: ConditionsSpec = Field(description="Policy conditions") 
    targets: TargetsSpec = Field(description="Policy targets")
    actions: List[ActionSpec] = Field(description="Policy actions")
    
    suppression_window: str = Field(default="5m", description="Suppression window duration")
    idempotency_window: str = Field(default="10m", description="Idempotency window duration") 
    notes: Optional[str] = Field(default=None, description="Free text notes")

    def compute_hash(self) -> str:
        """Compute SHA256 hash of normalized spec."""
        # Create normalized dict for hashing
        normalized = self.model_dump(by_alias=True, exclude_unset=False)
        # Sort keys recursively for deterministic hash
        json_str = json.dumps(normalized, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_str.encode()).hexdigest()


# ===== IR Models (Compiled) =====

class ResolvedTargets(BaseModel):
    """Resolved target IDs from selector."""
    host_id: UUID = Field(description="Target host UUID")
    target_type: str = Field(description="Target type")
    selector: SelectorSpec = Field(description="Original selector")
    resolved_ids: List[str] = Field(default_factory=list, description="Resolved canonical IDs")
    resolved_at: Optional[datetime] = Field(default=None, description="Resolution timestamp")


class CompiledTrigger(BaseModel):
    """Normalized trigger for IR."""
    type: str = Field(description="Trigger type")
    conditions: Dict[str, Any] = Field(description="Normalized trigger conditions")


class CompiledTriggerGroup(BaseModel):
    """Compiled trigger group."""
    logic: TriggerLogic = Field(description="Group logic")
    triggers: List[CompiledTrigger] = Field(description="Normalized triggers")


class CompiledCondition(BaseModel):
    """Normalized condition for IR."""
    scope: str = Field(description="Condition scope")
    field: str = Field(description="Field name")
    op: str = Field(description="Operator")
    value: Union[int, float, str, bool] = Field(description="Value")


class CompiledMatch(BaseModel):
    """Compiled matching logic."""
    trigger_group: CompiledTriggerGroup = Field(description="Compiled trigger group")
    conditions: List[CompiledCondition] = Field(description="Compiled conditions")


class CompiledAction(BaseModel):
    """Compiled action plan."""
    capability: str = Field(description="Capability ID")
    verb: str = Field(description="Action verb") 
    params: Dict[str, Any] = Field(description="Action parameters")


class WindowsConfig(BaseModel):
    """Policy execution windows."""
    suppression_s: int = Field(description="Suppression window in seconds")
    idempotency_s: int = Field(description="Idempotency window in seconds")


class PolicyIR(BaseModel):
    """Compiled intermediate representation."""
    policy_id: UUID = Field(description="Policy UUID")
    hash: str = Field(description="Spec hash")
    version_int: int = Field(description="Version number")
    priority: int = Field(description="Execution priority")
    stop_on_match: bool = Field(description="Stop on match flag")
    dynamic_resolution: bool = Field(description="Dynamic resolution flag")
    
    match: CompiledMatch = Field(description="Compiled matching logic")
    targets: ResolvedTargets = Field(description="Resolved targets")
    plan: List[CompiledAction] = Field(description="Compiled action plan")
    windows: WindowsConfig = Field(description="Execution windows")


# ===== Validation Models =====

class ValidationIssue(BaseModel):
    """Validation issue with JSON pointer path."""
    path: str = Field(description="JSON pointer path to issue")
    message: str = Field(description="Human-readable error message")


class ValidationResult(BaseModel):
    """Policy validation result."""
    ok: bool = Field(description="Overall validation success")
    schema: List[ValidationIssue] = Field(default_factory=list, description="Schema validation issues")
    compile: List[ValidationIssue] = Field(default_factory=list, description="Compilation issues")
    ir: Optional[PolicyIR] = Field(default=None, description="Compiled IR if successful")
    hash: Optional[str] = Field(default=None, description="Spec hash if valid")


# ===== Dry-run Models =====

class Precondition(BaseModel):
    """Driver precondition check."""
    check: str = Field(description="Check name")
    ok: bool = Field(description="Check result")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional check details")


class ExecutionPlan(BaseModel):
    """Driver execution plan."""
    kind: str = Field(description="Plan type: cli, api, ssh")
    preview: Union[List[str], List[Dict[str, Any]]] = Field(description="Plan preview")


class TargetEffect(BaseModel):
    """Per-target execution effect."""
    id: str = Field(description="Target ID")
    from_state: Optional[Dict[str, Any]] = Field(default=None, description="Current state", alias="from")
    to_state: Optional[Dict[str, Any]] = Field(default=None, description="Target state", alias="to")


class ExecutionEffects(BaseModel):
    """Driver execution effects."""
    summary: str = Field(description="Human-readable summary")
    per_target: List[TargetEffect] = Field(description="Per-target effects")


class DryRunResult(BaseModel):
    """Standardized dry-run result from drivers."""
    ok: bool = Field(description="Dry-run success")
    severity: Severity = Field(description="Result severity")
    idempotency_key: str = Field(description="Idempotency key")
    preconditions: List[Precondition] = Field(description="Precondition checks")
    plan: ExecutionPlan = Field(description="Execution plan")
    effects: ExecutionEffects = Field(description="Expected effects")
    reason: Optional[str] = Field(default=None, description="Additional context")


class TargetDryRunResult(BaseModel):
    """Per-target dry-run result."""
    target_id: str = Field(description="Target canonical ID")
    capability: str = Field(description="Capability ID")
    verb: str = Field(description="Action verb")
    driver: str = Field(description="Driver name")
    ok: bool = Field(description="Success flag")
    severity: Severity = Field(description="Result severity")
    idempotency_key: str = Field(description="Idempotency key")
    preconditions: List[Precondition] = Field(description="Precondition checks")
    plan: ExecutionPlan = Field(description="Execution plan")
    effects: ExecutionEffects = Field(description="Expected effects")
    reason: Optional[str] = Field(default=None, description="Failure/warning reason")


class InventoryInfo(BaseModel):
    """Inventory refresh information."""
    refreshed: bool = Field(description="Was inventory refreshed")
    ts: datetime = Field(description="Refresh timestamp")
    stale: bool = Field(default=False, description="Is inventory stale")


class PolicyDryRunResult(BaseModel):
    """Complete policy dry-run result."""
    severity: Severity = Field(description="Overall severity")
    results: List[TargetDryRunResult] = Field(description="Per-target results")
    transcript_id: UUID = Field(default_factory=uuid4, description="Unique transcript ID")
    used_inventory: InventoryInfo = Field(description="Inventory usage info")


# ===== Execution Models =====

class ExecutionSummary(BaseModel):
    """Policy execution summary for storage."""
    id: UUID = Field(default_factory=uuid4, description="Execution ID")
    policy_id: UUID = Field(description="Policy ID")
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Execution timestamp")
    severity: Severity = Field(description="Execution severity")
    event_snapshot: Dict[str, Any] = Field(description="Triggering event snapshot")
    actions: List[Dict[str, Any]] = Field(description="Executed actions summary")
    summary: str = Field(description="Human-readable summary")


# ===== Inverse Policy Models =====

class NeedsInput(BaseModel):
    """Fields requiring user input for inverse policy."""
    path: str = Field(description="JSON pointer to field requiring input")
    reason: str = Field(description="Why input is needed")


class InverseResult(BaseModel):
    """Inverse policy creation result."""
    spec_inverse: PolicySpec = Field(description="Generated inverse policy spec")
    enabled: bool = Field(default=False, description="Inverse policy enabled state")
    needs_input: List[NeedsInput] = Field(description="Fields requiring user input")
    notes: str = Field(description="Generated notes explaining inverse")


# ===== Host Capability Models =====

class CapabilityVerb(BaseModel):
    """Capability verb definition."""
    verb: str = Field(description="Verb name")
    inverse: Optional[str] = Field(default=None, description="Inverse verb name")


class HostCapability(BaseModel):
    """Host capability information."""
    id: str = Field(description="Capability ID")
    verbs: List[str] = Field(description="Available verbs")
    invertible: Dict[str, CapabilityVerb] = Field(default_factory=dict, description="Invertible verb mappings")
    idempotency: Optional[Dict[str, Any]] = Field(default=None, description="Idempotency configuration")
    dry_run: bool = Field(default=True, description="Supports dry-run")


class HostCapabilities(BaseModel):
    """Host capabilities response."""
    host_id: UUID = Field(description="Host UUID")
    capabilities: List[HostCapability] = Field(description="Available capabilities")
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Capability timestamp")


# ===== Inventory Models =====

class TargetInfo(BaseModel):
    """Individual target information."""
    id: str = Field(description="Canonical target ID")
    name: str = Field(description="Human-readable name")
    labels: Dict[str, str] = Field(default_factory=dict, description="Searchable labels")
    friendly: str = Field(description="Friendly display name")


class HostInventory(BaseModel):
    """Host inventory response."""
    host_id: UUID = Field(description="Host UUID")
    targets: List[TargetInfo] = Field(description="Available targets")
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Inventory timestamp")
    stale: bool = Field(default=False, description="Is inventory stale")


# ===== Event Models =====

class EventSubject(BaseModel):
    """Event subject reference."""
    kind: str = Field(description="Subject kind: ups, host, vm, integration")
    id: str = Field(description="Subject ID (UUID or provider ID)")


class NormalizedEvent(BaseModel):
    """Normalized event for policy matching."""
    type: str = Field(description="Event type: ups, metric, timer, webhook")
    kind: str = Field(description="Event kind: ups.state, metric.threshold, etc.")
    subject: EventSubject = Field(description="Event subject")
    attrs: Dict[str, Any] = Field(description="Event attributes")
    ts: datetime = Field(description="Event timestamp")
    correlation_id: Optional[UUID] = Field(default=None, description="Correlation ID")