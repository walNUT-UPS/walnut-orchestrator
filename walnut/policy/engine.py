"""
Policy Runtime Engine.

This module implements the policy execution engine that matches events against
policies, handles suppression/idempotency, and executes policy actions as
specified in POLICY.md.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4
import logging

from walnut.policy.models import (
    NormalizedEvent, PolicyIR, ExecutionSummary, Severity,
    PolicyDryRunResult, TargetDryRunResult
)
from walnut.database.models import PolicyV1, PolicyExecution


logger = logging.getLogger(__name__)


class PolicyEngine:
    """
    Policy runtime engine for event matching and execution.
    
    Handles event processing, policy matching, suppression/idempotency,
    and action execution as specified in POLICY.md.
    """

    def __init__(self, driver_manager=None, inventory_index=None):
        """
        Initialize policy engine.
        
        Args:
            driver_manager: Driver manager for action execution
            inventory_index: Inventory index for target resolution
        """
        self.driver_manager = driver_manager
        self.inventory_index = inventory_index
        
        # Per-host execution queues to avoid conflicts
        self._host_queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._host_workers: Dict[str, asyncio.Task] = {}
        
        # Execution tracking for suppression/idempotency
        self._execution_history: List[Dict[str, Any]] = []
        self._max_history = 1000  # Keep last N executions for suppression checks
        
        # Global concurrency limit
        self._global_semaphore = asyncio.Semaphore(10)

    async def process_event(self, event: NormalizedEvent) -> List[ExecutionSummary]:
        """
        Process normalized event against all policies.
        
        Args:
            event: Normalized event to process
            
        Returns:
            List of execution summaries for triggered policies
        """
        logger.info(f"Processing event: {event.type}.{event.kind} from {event.subject.id}")
        
        # Get candidate policies
        candidate_policies = await self._get_candidate_policies(event)
        if not candidate_policies:
            logger.debug("No candidate policies found for event")
            return []

        # Sort by priority (lower = higher priority), then by UUID for determinism
        sorted_policies = sorted(candidate_policies, key=lambda p: (p.priority, p.id))
        
        executions = []
        stop_processing = False
        
        for policy_data in sorted_policies:
            if stop_processing:
                break
                
            try:
                policy_ir = PolicyIR.model_validate(policy_data.compiled_ir)
                
                # Check if policy matches event
                if not await self._matches_policy(event, policy_ir):
                    continue
                    
                # Check suppression window
                if await self._is_suppressed(policy_ir, event):
                    execution = ExecutionSummary(
                        policy_id=policy_ir.policy_id,
                        severity=Severity.INFO,
                        event_snapshot=event.model_dump(),
                        actions=[],
                        summary="Suppressed due to suppression window"
                    )
                    executions.append(execution)
                    continue
                
                # Check idempotency window
                if await self._is_idempotent(policy_ir, event):
                    execution = ExecutionSummary(
                        policy_id=policy_ir.policy_id,
                        severity=Severity.INFO,
                        event_snapshot=event.model_dump(),
                        actions=[],
                        summary="Suppressed due to idempotency window"
                    )
                    executions.append(execution)
                    continue
                
                # Execute policy
                execution = await self._execute_policy(policy_ir, event)
                executions.append(execution)
                
                # Check stop_on_match
                if policy_ir.stop_on_match and execution.actions:
                    stop_processing = True
                    
            except Exception as e:
                logger.error(f"Error processing policy {policy_data.id}: {str(e)}")
                execution = ExecutionSummary(
                    policy_id=policy_data.id,
                    severity=Severity.ERROR,
                    event_snapshot=event.model_dump(),
                    actions=[],
                    summary=f"Policy execution failed: {str(e)}"
                )
                executions.append(execution)

        return executions

    async def dry_run_policy(self, policy_ir: PolicyIR, refresh_inventory: bool = True) -> PolicyDryRunResult:
        """
        Perform dry-run of policy against current system state.
        
        Args:
            policy_ir: Compiled policy IR
            refresh_inventory: Whether to refresh inventory first
            
        Returns:
            PolicyDryRunResult with dry-run details
        """
        logger.info(f"Starting dry-run for policy {policy_ir.policy_id}")
        
        try:
            # Refresh inventory if requested
            inventory_info = {"refreshed": False, "ts": datetime.now(timezone.utc), "stale": False}
            
            if refresh_inventory and self.inventory_index:
                try:
                    refresh_sla = 5  # Default SLA in seconds
                    success = await self.inventory_index.refresh_host_fast(
                        policy_ir.targets.host_id, 
                        refresh_sla
                    )
                    inventory_info["refreshed"] = success
                    inventory_info["stale"] = not success
                except Exception as e:
                    logger.warning(f"Inventory refresh failed: {str(e)}")
                    inventory_info["stale"] = True

            # Resolve targets if dynamic resolution enabled
            resolved_targets = policy_ir.targets
            if policy_ir.dynamic_resolution and self.inventory_index:
                try:
                    resolved_ids = await self._resolve_targets_dynamic(policy_ir.targets)
                    resolved_targets.resolved_ids = resolved_ids
                    resolved_targets.resolved_at = datetime.now(timezone.utc)
                except Exception as e:
                    logger.warning(f"Dynamic target resolution failed: {str(e)}")

            # Perform dry-run for each action/target combination
            results = []
            overall_severity = Severity.INFO
            
            for action in policy_ir.plan:
                for target_id in resolved_targets.resolved_ids:
                    try:
                        result = await self._dry_run_action(
                            action, target_id, resolved_targets.host_id
                        )
                        results.append(result)
                        
                        # Update overall severity
                        if result.severity == Severity.ERROR:
                            overall_severity = Severity.ERROR
                        elif result.severity == Severity.WARN and overall_severity != Severity.ERROR:
                            overall_severity = Severity.WARN
                            
                    except Exception as e:
                        error_result = TargetDryRunResult(
                            target_id=target_id,
                            capability=action.capability,
                            verb=action.verb,
                            driver="unknown",
                            ok=False,
                            severity=Severity.ERROR,
                            idempotency_key=f"{action.capability}:{action.verb}:{target_id}",
                            preconditions=[],
                            plan={"kind": "unknown", "preview": []},
                            effects={"summary": "Dry-run failed", "per_target": []},
                            reason=f"Dry-run error: {str(e)}"
                        )
                        results.append(error_result)
                        overall_severity = Severity.ERROR

            return PolicyDryRunResult(
                severity=overall_severity,
                results=results,
                transcript_id=uuid4(),
                used_inventory=inventory_info
            )
            
        except Exception as e:
            logger.error(f"Policy dry-run failed: {str(e)}")
            return PolicyDryRunResult(
                severity=Severity.ERROR,
                results=[],
                transcript_id=uuid4(),
                used_inventory={"refreshed": False, "ts": datetime.now(timezone.utc), "stale": True}
            )

    async def _get_candidate_policies(self, event: NormalizedEvent) -> List[PolicyV1]:
        """Get policies that might match the event based on trigger type."""
        # This would query the database for policies with matching trigger types
        # For now, return empty list as placeholder
        return []

    async def _matches_policy(self, event: NormalizedEvent, policy_ir: PolicyIR) -> bool:
        """
        Check if event matches policy trigger group and conditions.
        
        Args:
            event: Normalized event
            policy_ir: Policy intermediate representation
            
        Returns:
            True if policy matches event
        """
        # Check trigger group
        trigger_matches = []
        
        for trigger in policy_ir.match.trigger_group.triggers:
            match = await self._matches_trigger(event, trigger.type, trigger.conditions)
            trigger_matches.append(match)
        
        # Apply trigger group logic
        if policy_ir.match.trigger_group.logic.value == "ALL":
            triggers_match = all(trigger_matches)
        else:  # ANY
            triggers_match = any(trigger_matches)
        
        if not triggers_match:
            return False
            
        # Check conditions (always AND logic)
        for condition in policy_ir.match.conditions:
            if not await self._matches_condition(event, condition):
                return False
                
        return True

    async def _matches_trigger(self, event: NormalizedEvent, trigger_type: str, conditions: Dict[str, Any]) -> bool:
        """Check if event matches a specific trigger."""
        if event.kind != trigger_type:
            return False
            
        # Check trigger-specific conditions
        for key, value in conditions.items():
            if key == "type":
                continue  # Already checked
                
            event_value = event.attrs.get(key)
            if key == "equals" and event_value != value:
                return False
            elif key == "op" and key in event.attrs:
                # Handle metric threshold matching
                if not self._check_threshold(event.attrs.get("value"), conditions.get("op"), conditions.get("value")):
                    return False
                    
        return True

    async def _matches_condition(self, event: NormalizedEvent, condition) -> bool:
        """Check if event matches a policy condition."""
        # This would check conditions against current system state
        # For now, return True as placeholder
        return True

    def _check_threshold(self, actual_value, operator: str, threshold_value) -> bool:
        """Check if actual value meets threshold condition."""
        if actual_value is None or threshold_value is None:
            return False
            
        try:
            actual = float(actual_value)
            threshold = float(threshold_value)
            
            if operator == ">":
                return actual > threshold
            elif operator == ">=":
                return actual >= threshold
            elif operator == "<":
                return actual < threshold
            elif operator == "<=":
                return actual <= threshold
            elif operator == "=":
                return actual == threshold
            elif operator == "!=":
                return actual != threshold
        except (ValueError, TypeError):
            return False
            
        return False

    async def _is_suppressed(self, policy_ir: PolicyIR, event: NormalizedEvent) -> bool:
        """Check if policy is within suppression window."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=policy_ir.windows.suppression_s)
        
        for execution in self._execution_history:
            if (execution.get("policy_id") == policy_ir.policy_id and
                execution.get("timestamp") and execution["timestamp"] > cutoff_time and
                execution.get("actions")):  # Only suppress if previous execution had actions
                return True
                
        return False

    async def _is_idempotent(self, policy_ir: PolicyIR, event: NormalizedEvent) -> bool:
        """Check if policy execution would be idempotent."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=policy_ir.windows.idempotency_s)
        
        # Build idempotency key for this execution
        current_key = self._build_idempotency_key(policy_ir, event)
        
        for execution in self._execution_history:
            if (execution.get("idempotency_key") == current_key and
                execution.get("timestamp") and execution["timestamp"] > cutoff_time):
                return True
                
        return False

    def _build_idempotency_key(self, policy_ir: PolicyIR, event: NormalizedEvent) -> str:
        """Build idempotency key for policy execution."""
        # Simple key based on policy, targets, and actions
        target_ids = ",".join(sorted(policy_ir.targets.resolved_ids))
        action_keys = ",".join(f"{a.capability}:{a.verb}" for a in policy_ir.plan)
        return f"{policy_ir.policy_id}:{target_ids}:{action_keys}"

    async def _execute_policy(self, policy_ir: PolicyIR, event: NormalizedEvent) -> ExecutionSummary:
        """Execute policy actions."""
        logger.info(f"Executing policy {policy_ir.policy_id}")
        
        try:
            # Resolve targets dynamically if enabled
            resolved_targets = policy_ir.targets
            if policy_ir.dynamic_resolution and self.inventory_index:
                resolved_ids = await self._resolve_targets_dynamic(policy_ir.targets)
                resolved_targets.resolved_ids = resolved_ids
                resolved_targets.resolved_at = datetime.now(timezone.utc)

            if not resolved_targets.resolved_ids:
                return ExecutionSummary(
                    policy_id=policy_ir.policy_id,
                    severity=Severity.WARN,
                    event_snapshot=event.model_dump(),
                    actions=[],
                    summary="No targets resolved for execution"
                )

            # Execute actions through host queue
            execution_results = []
            host_id = str(resolved_targets.host_id)
            
            # Queue execution on host-specific queue
            execution_task = asyncio.create_task(
                self._execute_on_host(policy_ir, resolved_targets, event)
            )
            
            try:
                results = await execution_task
                execution_results.extend(results)
            except Exception as e:
                logger.error(f"Host execution failed: {str(e)}")
                execution_results.append({
                    "action": "execution_error", 
                    "result": str(e),
                    "success": False
                })

            # Determine overall execution severity
            has_errors = any(not r.get("success", True) for r in execution_results)
            has_actions = bool(execution_results)
            
            if has_errors:
                severity = Severity.ERROR
            elif has_actions:
                severity = Severity.INFO
            else:
                severity = Severity.WARN

            summary = f"Executed {len(execution_results)} actions"
            if has_errors:
                error_count = sum(1 for r in execution_results if not r.get("success", True))
                summary += f" ({error_count} failed)"

            execution = ExecutionSummary(
                policy_id=policy_ir.policy_id,
                severity=severity,
                event_snapshot=event.model_dump(),
                actions=execution_results,
                summary=summary
            )

            # Record in history
            self._record_execution(execution, policy_ir, event)

            return execution

        except Exception as e:
            logger.error(f"Policy execution failed: {str(e)}")
            return ExecutionSummary(
                policy_id=policy_ir.policy_id,
                severity=Severity.ERROR,
                event_snapshot=event.model_dump(),
                actions=[],
                summary=f"Execution failed: {str(e)}"
            )

    async def _resolve_targets_dynamic(self, targets) -> List[str]:
        """Dynamically resolve target selector to current IDs."""
        if not self.inventory_index:
            return targets.resolved_ids

        try:
            # Get current inventory
            inventory = await self.inventory_index.get_host_inventory(targets.host_id)
            
            # Filter by target type and resolve selector
            type_targets = [t for t in inventory.targets if targets.target_type in t.id]
            
            # Simple resolution logic (would be more sophisticated in production)
            if targets.selector.mode.value == "list":
                items = [item.strip() for item in targets.selector.value.split(",")]
                resolved = []
                for item in items:
                    for target in type_targets:
                        if target.name == item or item in target.id:
                            resolved.append(target.id)
                return resolved
            else:
                # For other modes, return first few targets as placeholder
                return [t.id for t in type_targets[:5]]
                
        except Exception as e:
            logger.warning(f"Dynamic target resolution failed: {str(e)}")
            return targets.resolved_ids

    async def _execute_on_host(self, policy_ir: PolicyIR, targets, event: NormalizedEvent) -> List[Dict[str, Any]]:
        """Execute policy actions on a specific host."""
        async with self._global_semaphore:
            results = []
            
            for action in policy_ir.plan:
                for target_id in targets.resolved_ids:
                    try:
                        result = await self._execute_action(
                            action, target_id, targets.host_id
                        )
                        results.append({
                            "action": f"{action.capability}:{action.verb}",
                            "target": target_id,
                            "result": result,
                            "success": result.get("ok", True)
                        })
                    except Exception as e:
                        results.append({
                            "action": f"{action.capability}:{action.verb}",
                            "target": target_id,
                            "result": str(e),
                            "success": False
                        })
            
            return results

    async def _execute_action(self, action, target_id: str, host_id: UUID) -> Dict[str, Any]:
        """Execute single action on target."""
        if not self.driver_manager:
            raise ValueError("Driver manager not available")
        
        # Get driver for host
        driver = await self.driver_manager.get_driver_for_host(host_id)
        if not driver:
            raise ValueError(f"No driver available for host {host_id}")

        # Map capability to driver method
        method_name = action.capability.replace(".", "_")
        if not hasattr(driver, method_name):
            raise ValueError(f"Driver method {method_name} not found")

        method = getattr(driver, method_name)
        
        # Create target object (simplified)
        target = {"external_id": target_id}
        
        # Execute action
        return await method(action.verb, target, dry_run=False)

    async def _dry_run_action(self, action, target_id: str, host_id: UUID) -> TargetDryRunResult:
        """Perform dry-run of single action."""
        try:
            if not self.driver_manager:
                raise ValueError("Driver manager not available")
            
            # Get driver for host
            driver = await self.driver_manager.get_driver_for_host(host_id)
            if not driver:
                raise ValueError(f"No driver available for host {host_id}")

            # Map capability to driver method
            method_name = action.capability.replace(".", "_")
            if not hasattr(driver, method_name):
                raise ValueError(f"Driver method {method_name} not found")

            method = getattr(driver, method_name)
            
            # Create target object (simplified)
            target = {"external_id": target_id}
            
            # Execute dry-run
            dry_run_result = await method(action.verb, target, dry_run=True)
            
            # Convert to standardized format
            return TargetDryRunResult(
                target_id=target_id,
                capability=action.capability,
                verb=action.verb,
                driver=driver.__class__.__name__,
                ok=dry_run_result.get("ok", True),
                severity=Severity(dry_run_result.get("severity", "info")),
                idempotency_key=dry_run_result.get("idempotency_key", f"{action.capability}:{action.verb}:{target_id}"),
                preconditions=dry_run_result.get("preconditions", []),
                plan=dry_run_result.get("plan", {"kind": "unknown", "preview": []}),
                effects=dry_run_result.get("effects", {"summary": "Unknown effects", "per_target": []}),
                reason=dry_run_result.get("reason")
            )
            
        except Exception as e:
            return TargetDryRunResult(
                target_id=target_id,
                capability=action.capability,
                verb=action.verb,
                driver="unknown",
                ok=False,
                severity=Severity.ERROR,
                idempotency_key=f"{action.capability}:{action.verb}:{target_id}",
                preconditions=[],
                plan={"kind": "unknown", "preview": []},
                effects={"summary": "Dry-run failed", "per_target": []},
                reason=f"Dry-run error: {str(e)}"
            )

    def _record_execution(self, execution: ExecutionSummary, policy_ir: PolicyIR, event: NormalizedEvent):
        """Record execution in history for suppression/idempotency tracking."""
        history_entry = {
            "policy_id": execution.policy_id,
            "timestamp": execution.ts,
            "idempotency_key": self._build_idempotency_key(policy_ir, event),
            "actions": execution.actions,
            "severity": execution.severity.value
        }
        
        self._execution_history.append(history_entry)
        
        # Prune old entries
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]

    async def shutdown(self):
        """Shutdown policy engine and cleanup resources."""
        # Cancel all host worker tasks
        for task in self._host_workers.values():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._host_workers.clear()
        logger.info("Policy engine shutdown complete")


# Utility functions

def create_policy_engine(driver_manager=None, inventory_index=None) -> PolicyEngine:
    """
    Create configured policy engine.
    
    Args:
        driver_manager: Driver manager for action execution
        inventory_index: Inventory index for target resolution
        
    Returns:
        Configured PolicyEngine instance
    """
    return PolicyEngine(driver_manager, inventory_index)