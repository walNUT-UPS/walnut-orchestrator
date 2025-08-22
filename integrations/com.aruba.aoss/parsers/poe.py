from __future__ import annotations

from typing import Dict
import re


def parse_poe_summary(output: str) -> Dict[str, float]:
    """Parse a minimal PoE power summary from CLI if SNMP is unavailable.
    Returns dict with keys: budget_w, used_w, free_w when possible.
    """
    budget = used = free = None
    for line in output.splitlines():
        m = re.search(r"\b(?:(Total|Power available))\b.*?(\d+(?:\.\d+)?)\s*W", line, re.I)
        if m and budget is None:
            budget = float(m.group(2))
        m = re.search(r"\b(Used|Consumption)\b.*?(\d+(?:\.\d+)?)\s*W", line, re.I)
        if m and used is None:
            used = float(m.group(2))
        m = re.search(r"\b(Free|Remaining)\b.*?(\d+(?:\.\d+)?)\s*W", line, re.I)
        if m and free is None:
            free = float(m.group(2))
    result: Dict[str, float] = {}
    if budget is not None:
        result["budget_w"] = budget
    if used is not None:
        result["used_w"] = used
    if free is not None:
        result["free_w"] = free
    return result

