"""
Policy compilation and validation pipeline.

This module implements the policy compilation pipeline that validates policy specs,
resolves target selectors, verifies capabilities, and produces intermediate 
representation (IR) for runtime execution.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from pydantic import ValidationError

from walnut.policy.models import (
    PolicySpec, PolicyIR, ValidationResult, ValidationIssue, 
    ResolvedTargets, CompiledMatch, CompiledTriggerGroup, CompiledTrigger,
    CompiledCondition, CompiledAction, WindowsConfig, Severity
)
from walnut.utils.timeparse import parse_duration


class PolicyCompiler:
    """
    Policy compiler that validates specs and produces executable IR.
    
    Handles schema validation, selector resolution, capability verification,
    and IR compilation as specified in POLICY.md.
    """

    def __init__(self, capability_resolver=None, inventory_resolver=None):
        """
        Initialize compiler with optional resolvers.
        
        Args:
            capability_resolver: Function to resolve host capabilities
            inventory_resolver: Function to resolve host inventory
        """
        self.capability_resolver = capability_resolver
        self.inventory_resolver = inventory_resolver

    def validate_and_compile(self, spec_dict: Dict[str, Any]) -> ValidationResult:
        """
        Validate policy spec and compile to IR.
        
        Args:
            spec_dict: Policy specification dictionary
            
        Returns:
            ValidationResult with validation issues and compiled IR
        """
        result = ValidationResult(ok=True)
        
        try:
            # Step 1: Schema validation
            spec = PolicySpec.model_validate(spec_dict)
            result.hash = spec.compute_hash()
            
        except ValidationError as e:
            result.ok = False
            for error in e.errors():
                path = "/" + "/".join(str(part) for part in error["loc"])
                result.schema.append(ValidationIssue(
                    path=path,
                    message=error["msg"]
                ))
            return result

        try:
            # Step 2: Compile validation
            ir = self._compile_spec(spec)
            result.ir = ir
            
        except CompilationError as e:
            result.ok = False
            result.compile.append(ValidationIssue(
                path=e.path,
                message=e.message
            ))
        except Exception as e:
            result.ok = False
            result.compile.append(ValidationIssue(
                path="/",
                message=f"Compilation error: {str(e)}"
            ))

        return result

    def _compile_spec(self, spec: PolicySpec) -> PolicyIR:
        """
        Compile validated spec to intermediate representation.
        
        Args:
            spec: Validated policy specification
            
        Returns:
            Compiled PolicyIR
            
        Raises:
            CompilationError: If compilation fails
        """
        policy_id = str(uuid4())
        
        # Compile matching logic
        match = self._compile_match(spec)
        
        # Resolve targets
        targets = self._resolve_targets(spec.targets)
        
        # Verify capabilities and compile actions
        actions = self._compile_actions(spec.actions, targets.host_id)
        
        # Parse time windows
        windows = self._compile_windows(spec.suppression_window, spec.idempotency_window)
        
        return PolicyIR(
            policy_id=policy_id,
            hash=spec.compute_hash(),
            version_int=1,
            priority=spec.priority,
            stop_on_match=spec.stop_on_match,
            dynamic_resolution=spec.dynamic_resolution,
            match=match,
            targets=targets,
            plan=actions,
            windows=windows
        )

    def _compile_match(self, spec: PolicySpec) -> CompiledMatch:
        """Compile trigger group and conditions."""
        # Compile trigger group
        compiled_triggers = []
        for trigger in spec.trigger_group.triggers:
            compiled_trigger = CompiledTrigger(
                type=trigger.type,
                conditions=self._normalize_trigger_conditions(trigger)
            )
            compiled_triggers.append(compiled_trigger)

        trigger_group = CompiledTriggerGroup(
            logic=spec.trigger_group.logic,
            triggers=compiled_triggers
        )

        # Compile conditions
        compiled_conditions = []
        for condition in spec.conditions.all:
            compiled_condition = CompiledCondition(
                scope=condition.scope,
                field=condition.field,
                op=condition.op,
                value=condition.value
            )
            compiled_conditions.append(compiled_condition)

        return CompiledMatch(
            trigger_group=trigger_group,
            conditions=compiled_conditions
        )

    def _normalize_trigger_conditions(self, trigger) -> Dict[str, Any]:
        """Normalize trigger to standard conditions format."""
        conditions = {"type": trigger.type}
        
        if trigger.equals is not None:
            conditions["equals"] = trigger.equals
            
        if trigger.metric is not None:
            conditions["metric"] = trigger.metric
            
        if trigger.op is not None:
            conditions["op"] = trigger.op
            
        if trigger.value is not None:
            conditions["value"] = trigger.value
            
        if trigger.for_duration is not None:
            conditions["for_s"] = parse_duration(trigger.for_duration)
            
        if trigger.schedule is not None:
            conditions["schedule"] = trigger.schedule.model_dump()
            
        if trigger.after is not None:
            conditions["after_s"] = parse_duration(trigger.after)
            
        if trigger.since_event is not None:
            conditions["since_event"] = trigger.since_event.model_dump()
            
        return conditions

    def _resolve_targets(self, targets_spec) -> ResolvedTargets:
        """
        Resolve target selector to canonical IDs.
        
        Args:
            targets_spec: Target specification
            
        Returns:
            ResolvedTargets with canonical IDs
            
        Raises:
            CompilationError: If target resolution fails
        """
        resolved_ids = []
        resolved_at = None
        
        # If we have an inventory resolver, resolve now
        if self.inventory_resolver:
            try:
                inventory = self.inventory_resolver(targets_spec.host_id, targets_spec.target_type)
                resolved_ids = self._expand_selector(
                    targets_spec.selector, 
                    inventory
                )
                resolved_at = datetime.now(timezone.utc)
            except Exception as e:
                raise CompilationError(
                    path="/targets/selector",
                    message=f"Failed to resolve targets: {str(e)}"
                )
        
        return ResolvedTargets(
            host_id=targets_spec.host_id,
            target_type=targets_spec.target_type,
            selector=targets_spec.selector,
            resolved_ids=resolved_ids,
            resolved_at=resolved_at
        )

    def _expand_selector(self, selector, inventory) -> List[str]:
        """
        Expand selector to canonical target IDs.
        
        Args:
            selector: Selector specification
            inventory: Available targets from inventory
            
        Returns:
            List of canonical target IDs
        """
        if selector.mode == "list":
            return self._expand_list_selector(selector.value, inventory)
        elif selector.mode == "range":
            return self._expand_range_selector(selector.value, inventory)
        elif selector.mode == "query":
            return self._expand_query_selector(selector.value, inventory)
        else:
            raise CompilationError(
                path="/targets/selector/mode",
                message=f"Unknown selector mode: {selector.mode}"
            )

    def _expand_list_selector(self, value: str, inventory) -> List[str]:
        """Expand comma-separated list selector."""
        items = [item.strip() for item in value.split(",")]
        resolved = []
        
        for item in items:
            if "-" in item and self._is_range_pattern(item):
                # Handle ranges within list (e.g., "1-4" in "1-4,6,8")
                resolved.extend(self._expand_range_pattern(item, inventory))
            else:
                # Direct lookup
                canonical_id = self._resolve_target_name(item, inventory)
                if canonical_id:
                    resolved.append(canonical_id)
                    
        return resolved

    def _expand_range_selector(self, value: str, inventory) -> List[str]:
        """Expand range selector (e.g., '104-108', '1/1-1/4')."""
        return self._expand_range_pattern(value, inventory)

    def _expand_range_pattern(self, pattern: str, inventory) -> List[str]:
        """
        Expand range pattern to canonical IDs.
        
        Supports:
        - Simple numeric ranges: 104-108
        - Port ranges: 1/1-1/4, 1/A1-1/B4
        """
        if re.match(r'^\d+-\d+$', pattern):
            # Simple numeric range
            start, end = map(int, pattern.split('-'))
            resolved = []
            for i in range(start, end + 1):
                canonical_id = self._resolve_target_name(str(i), inventory)
                if canonical_id:
                    resolved.append(canonical_id)
            return resolved
            
        elif re.match(r'^[\d/A-Z]+-[\d/A-Z]+$', pattern):
            # Port range pattern (complex parsing needed)
            return self._expand_port_range(pattern, inventory)
            
        else:
            raise CompilationError(
                path="/targets/selector/value",
                message=f"Unsupported range pattern: {pattern}"
            )

    def _expand_port_range(self, pattern: str, inventory) -> List[str]:
        """Expand port range patterns like '1/1-1/4' or '1/A1-1/B4'."""
        # This would need more sophisticated parsing for real port ranges
        # For now, return empty list and let dynamic resolution handle it
        return []

    def _expand_query_selector(self, value: str, inventory) -> List[str]:
        """Expand query selector (not implemented in this version)."""
        raise CompilationError(
            path="/targets/selector/mode",
            message="Query selector mode not implemented in v1"
        )

    def _is_range_pattern(self, value: str) -> bool:
        """Check if value looks like a range pattern."""
        return bool(re.match(r'^.*-.*$', value))

    def _resolve_target_name(self, name: str, inventory) -> Optional[str]:
        """Resolve target name to canonical ID using inventory."""
        for target in inventory:
            if target.get("name") == name or target.get("id") == name:
                return target.get("canonical_id", target.get("id"))
        return None

    def _compile_actions(self, actions_spec: List, host_id: str) -> List[CompiledAction]:
        """
        Compile and verify actions against host capabilities.
        
        Args:
            actions_spec: List of action specifications
            host_id: Target host UUID
            
        Returns:
            List of compiled actions
            
        Raises:
            CompilationError: If actions are invalid
        """
        compiled_actions = []
        
        # Get host capabilities if resolver available
        host_capabilities = {}
        if self.capability_resolver:
            try:
                host_capabilities = self.capability_resolver(host_id)
            except Exception as e:
                raise CompilationError(
                    path="/actions",
                    message=f"Failed to resolve host capabilities: {str(e)}"
                )

        for i, action in enumerate(actions_spec):
            # Verify capability exists
            if host_capabilities and action.capability_id not in host_capabilities:
                raise CompilationError(
                    path=f"/actions/{i}/capability_id",
                    message=f"Unknown capability: {action.capability_id}"
                )

            # Verify verb exists for capability
            capability_info = host_capabilities.get(action.capability_id, {})
            available_verbs = capability_info.get("verbs", [])
            if available_verbs and action.verb not in available_verbs:
                raise CompilationError(
                    path=f"/actions/{i}/verb",
                    message=f"Unknown verb '{action.verb}' for capability '{action.capability_id}'"
                )

            compiled_action = CompiledAction(
                capability=action.capability_id,
                verb=action.verb,
                params=action.params
            )
            compiled_actions.append(compiled_action)

        return compiled_actions

    def _compile_windows(self, suppression_window: str, idempotency_window: str) -> WindowsConfig:
        """Parse time window durations."""
        try:
            suppression_s = parse_duration(suppression_window)
            idempotency_s = parse_duration(idempotency_window)
            
            return WindowsConfig(
                suppression_s=suppression_s,
                idempotency_s=idempotency_s
            )
        except ValueError as e:
            raise CompilationError(
                path="/suppression_window",
                message=f"Invalid time duration: {str(e)}"
            )


class CompilationError(Exception):
    """Exception raised during policy compilation."""
    
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


# Utility functions

def validate_policy_spec(spec_dict: Dict[str, Any]) -> ValidationResult:
    """
    Validate policy specification without compilation.
    
    Args:
        spec_dict: Policy specification dictionary
        
    Returns:
        ValidationResult with schema validation only
    """
    compiler = PolicyCompiler()
    return compiler.validate_and_compile(spec_dict)


def compile_policy(spec_dict: Dict[str, Any], 
                  capability_resolver=None,
                  inventory_resolver=None) -> ValidationResult:
    """
    Compile policy specification to IR with full validation.
    
    Args:
        spec_dict: Policy specification dictionary
        capability_resolver: Function to resolve host capabilities
        inventory_resolver: Function to resolve host inventory
        
    Returns:
        ValidationResult with compiled IR if successful
    """
    compiler = PolicyCompiler(capability_resolver, inventory_resolver)
    return compiler.validate_and_compile(spec_dict)


def compute_spec_hash(spec_dict: Dict[str, Any]) -> str:
    """
    Compute deterministic hash of policy specification.
    
    Args:
        spec_dict: Policy specification dictionary
        
    Returns:
        SHA256 hash string
    """
    # Normalize spec for hashing
    normalized = json.dumps(spec_dict, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(normalized.encode()).hexdigest()


def normalize_spec(spec_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize policy specification for consistent processing.
    
    Args:
        spec_dict: Raw policy specification
        
    Returns:
        Normalized specification dictionary
    """
    try:
        spec = PolicySpec.model_validate(spec_dict)
        return spec.model_dump(by_alias=True, exclude_unset=False)
    except ValidationError:
        # Return original if normalization fails
        return spec_dict


# Time duration parsing helpers

def parse_time_windows(suppression: str, idempotency: str) -> Tuple[int, int]:
    """
    Parse time window strings to seconds.
    
    Args:
        suppression: Suppression window (e.g., "5m")
        idempotency: Idempotency window (e.g., "10m")
        
    Returns:
        Tuple of (suppression_seconds, idempotency_seconds)
    """
    suppression_s = parse_duration(suppression)
    idempotency_s = parse_duration(idempotency)
    return suppression_s, idempotency_s