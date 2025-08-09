from .schemas import PolicySchema, CompiledPlan, CompiledStep
from walnut.utils.timeparse import parse_time
from typing import Dict, Any, Optional, List

def resolve_targets(policy: PolicySchema) -> List[str]:
    """
    Placeholder target resolver.
    """
    selector = policy.targets.selector
    if selector.hosts or selector.tags or selector.types:
        # In a real implementation, this would query the database
        # based on the selector. For now, we return a placeholder.
        return ["host1.example.com", "host2.example.com"]
    return []

def compile_plan(policy: PolicySchema, event: Optional[Dict[str, Any]] = None, policy_id: Optional[int] = None) -> CompiledPlan:
    """
    Compile a policy and an event into a structured plan.
    This is a pure function with no I/O.
    """
    resolved_targets = resolve_targets(policy)

    compiled_steps = []
    step_no_counter = 1
    for target in resolved_targets:
        for step in policy.steps:
            compiled_steps.append(CompiledStep(
                step_no=step_no_counter,
                type=step.type,
                params=step.params,
                target=target,
                timeout=parse_time(step.timeout) if step.timeout else 120,
                retries=step.retries or 0,
                backoff=parse_time(step.backoff) if step.backoff else 10,
                continue_on_error=step.continue_on_error or False,
            ))
            step_no_counter += 1

    # Placeholder for suppression logic
    # In a real implementation, this would check the policy_runs table.
    would_be_suppressed = False

    plan = CompiledPlan(
        policy_name=policy.name,
        policy_id=policy_id,
        event=event,
        targets=resolved_targets,
        steps=compiled_steps,
        would_be_suppressed=would_be_suppressed,
    )

    return plan
