from typing import Dict, List, Any, Optional
from walnut.utils.timeparse import parse_time


def _safe_get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    try:
        for p in path:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                return default
        return cur if cur is not None else default
    except Exception:
        return default


def _lint_v1(spec: Dict[str, Any]) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    name = spec.get("name")
    if not name or not str(name).strip():
        errors.append("Policy name cannot be empty.")

    # triggers
    triggers = _safe_get(spec, ["trigger_group", "triggers"], [])
    if not isinstance(triggers, list) or len(triggers) == 0:
        errors.append("At least one trigger is required.")

    # actions
    actions = spec.get("actions", [])
    if not isinstance(actions, list) or len(actions) == 0:
        errors.append("At least one action is required.")
    else:
        for i, a in enumerate(actions):
            if not isinstance(a, dict):
                errors.append(f"Action {i+1} is not an object.")
                continue
            if not a.get("capability_id"):
                errors.append(f"Action {i+1} missing capability_id.")
            if not a.get("verb"):
                errors.append(f"Action {i+1} missing verb.")

    # targets
    targets = spec.get("targets", {}) or {}
    if not targets or not targets.get("host_id"):
        warnings.append("No host selected in targets; target resolution may fail.")

    # safeties/limits
    sup = spec.get("suppression_window")
    if sup:
        try:
            seconds = parse_time(str(sup))
            if seconds > 24 * 3600:
                warnings.append("Suppression window is very large (> 24h).")
        except Exception:
            errors.append(f"Invalid suppression_window: {sup}")

    idem = spec.get("idempotency_window")
    if idem:
        try:
            parse_time(str(idem))
        except Exception:
            errors.append(f"Invalid idempotency_window: {idem}")

    return {"errors": errors, "warnings": warnings}


def _lint_v2(spec: Dict[str, Any]) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    name = spec.get("name")
    if not name or not str(name).strip():
        errors.append("Policy name cannot be empty.")

    trigger = spec.get("trigger") or {}
    if not isinstance(trigger, dict) or not trigger.get("type"):
        errors.append("Trigger type is missing.")

    actions = spec.get("actions", [])
    if not isinstance(actions, list) or len(actions) == 0:
        errors.append("At least one action is required.")
    else:
        for i, a in enumerate(actions):
            if not isinstance(a, dict):
                errors.append(f"Action {i+1} is not an object.")
                continue
            if not a.get("capability"):
                errors.append(f"Action {i+1} missing capability.")
            if not a.get("verb"):
                errors.append(f"Action {i+1} missing verb.")
            # Disallow non-policy/editor capabilities
            if a.get("capability") == "inventory.list":
                errors.append(f"Action {i+1} uses unsupported capability 'inventory.list'.")
            # Host-only caps shouldn't require selector
            if a.get("capability") == "power.control":
                sel = a.get("selector") or {}
                if sel and any(sel.get(k) for k in ("external_ids", "names", "labels", "attrs")):
                    errors.append(f"Action {i+1} is host-only but has a target selector.")
                if not a.get("host_id"):
                    errors.append(f"Action {i+1} (host-only) requires host_id.")
            # VM lifecycle must have identifiers
            if a.get("capability") == "vm.lifecycle":
                sel = a.get("selector") or {}
                ids = (sel.get("external_ids") or sel.get("names") or [])
                if not ids:
                    errors.append(f"Action {i+1} requires target identifiers for vm.lifecycle.")
                if not a.get("host_id"):
                    errors.append(f"Action {i+1} requires host_id for vm.lifecycle.")

    safeties = spec.get("safeties", {}) or {}
    sup = safeties.get("suppression_window")
    if sup:
        try:
            seconds = parse_time(str(sup))
            if seconds > 24 * 3600:
                warnings.append("Suppression window is very large (> 24h).")
        except Exception:
            errors.append(f"Invalid suppression_window: {sup}")

    return {"errors": errors, "warnings": warnings}


def lint_policy(policy: Any) -> Dict[str, List[str]]:
    """
    Tolerant linter supporting both legacy v1 and new v2 policy shapes.

    Returns a consistent {"errors": [], "warnings": []} structure.
    """
    try:
        if hasattr(policy, "model_dump"):
            spec = policy.model_dump()  # pydantic model -> dict
        elif isinstance(policy, dict):
            spec = policy
        else:
            # Best-effort conversion
            spec = dict(policy or {})
    except Exception:
        spec = {}

    # Heuristics to detect shape
    if "trigger_group" in spec or spec.get("version") in (1, "1", "1.0"):
        return _lint_v1(spec)
    else:
        return _lint_v2(spec)
