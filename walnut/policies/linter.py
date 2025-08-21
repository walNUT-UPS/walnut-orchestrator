from .schemas import PolicySchema
from walnut.utils.timeparse import parse_time
from typing import Dict, List, Any

def lint_policy(policy: PolicySchema) -> Dict[str, List[str]]:
    errors = []
    warnings = []

    # Errors
    if not policy.name:
        errors.append("Policy name cannot be empty.")
    if not policy.actions:
        errors.append("Policy must have at least one action.")
    if not policy.trigger.type:
        errors.append("Trigger type is missing.")

    for i, action in enumerate(policy.actions):
        if action.capability == "ssh" and action.verb == "shutdown" and not policy.safeties.global_lock and not policy.safeties.never_hosts:
            warnings.append(f"Action {i+1} ('{action.capability}.{action.verb}') is a destructive action but has no safeties like 'global_lock' or 'never_hosts'.")

    # Warnings
    if policy.safeties.suppression_window:
        try:
            suppression_seconds = parse_time(policy.safeties.suppression_window)
            if suppression_seconds > 3600 * 24:  # 24 hours
                warnings.append("Suppression window is very large (more than 24 hours).")
        except ValueError:
            errors.append(f"Invalid format for suppression_window: '{policy.safeties.suppression_window}'")

    return {"errors": errors, "warnings": warnings}
