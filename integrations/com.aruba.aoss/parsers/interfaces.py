from __future__ import annotations

import re
from typing import Dict, List


def parse_show_version(output: str) -> Dict[str, str]:
    """Parse minimal details from 'show version'.
    Returns dict(model, version, serial?) when possible.
    """
    model = None
    version = None
    serial = None
    for line in output.splitlines():
        if not model:
            m = re.search(r"(Aruba|HP|HPE)\s*(?:Switch)?\s*([\w\-]+)", line, re.I)
            if m:
                model = m.group(2)
        if not version:
            m = re.search(r"(KA|WC|WB|YA|YB|YC|KB|K.?)\.[\w\.\-]+|ArubaOS\s*([\w\.\-]+)", line)
            if m:
                version = m.group(0)
        if not serial:
            m = re.search(r"Serial\s*(?:Number|No\.)\s*[:#]?\s*(\S+)", line, re.I)
            if m:
                serial = m.group(1)
    return {"model": model or "unknown", "version": version or "unknown", "serial": serial or "unknown"}


def parse_show_modules(output: str) -> List[str]:
    """Parse 'show modules' to find slot letters present."""
    slots: List[str] = []
    for line in output.splitlines():
        m = re.search(r"\bSlot\s+([A-Z])\b", line)
        if m:
            s = m.group(1)
            if s not in slots:
                slots.append(s)
        m = re.search(r"\b([A-Z])\s+Module", line)
        if m:
            s = m.group(1)
            if s not in slots:
                slots.append(s)
    return slots


def parse_show_vsf(output: str) -> Dict[str, object]:
    """Parse 'show vsf' to detect members and roles."""
    members = 0
    roles: List[str] = []
    for line in output.splitlines():
        m = re.search(r"Member\s+(\d+)\s+.*\b(Role|Type)\b\s*[:\-]?\s*(\w+)", line, re.I)
        if m:
            members = max(members, int(m.group(1)))
            roles.append(m.group(3).lower())
        # common table with columns: Member | Status | ... | Role
        m = re.search(r"^\s*(\d+)\s+\S+\s+\S+\s+\S+\s+(Commander|Standby|Member)\b", line, re.I)
        if m:
            members = max(members, int(m.group(1)))
            roles.append(m.group(2).lower())
    return {"members": members or (1 if roles else 0), "roles": roles}

