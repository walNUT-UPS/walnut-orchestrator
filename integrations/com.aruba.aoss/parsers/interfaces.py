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


def parse_show_stack(output: str) -> Dict[str, object]:
    """Parse 'show stack' to detect members and roles.
    
    Example output:
    Stack ID         : 00027010-6f8ed480
    MAC Address      : 70106f-8ed4c4
    Stack Topology   : Chain
    Stack Status     : Fragment Active
    Split Policy     : One-Fragment-Up
    Uptime           : 23d 6h 19m
    Software Version : KB.16.11.0025

     Mbr
     ID  Mac Address       Model                                 Pri Status
     --- ----------------- ------------------------------------- --- ---------------
      1  70106f-8ed480     Aruba JL076A 3810M-40G-8SR-PoE+-1-... 128 Commander
      2  9457a5-8ce600     Aruba JL075A 3810M-16SFP+-2-slot S... 128 Missing
    """
    members = []
    in_member_table = False
    
    for line in output.splitlines():
        # Look for member table header
        if re.search(r"^\s*Mbr\s*$", line) or re.search(r"^\s*ID\s+Mac Address", line):
            in_member_table = True
            continue
        
        # Skip separator line
        if re.search(r"^\s*---", line):
            continue
        
        # Parse member lines when in table
        if in_member_table:
            # Match: "  1  70106f-8ed480     Aruba JL076A 3810M-40G-8SR-PoE+-1-... 128 Commander"
            m = re.search(r"^\s*(\d+)\s+([a-f0-9-]+)\s+(.+?)\s+(\d+)\s+(Commander|Standby|Member|Missing)\s*$", line, re.I)
            if m:
                member_id = m.group(1)
                mac_address = m.group(2)
                model = m.group(3).strip()
                priority = m.group(4)
                status = m.group(5).lower()
                
                # Clean up model name (remove trailing dots if truncated)
                model = re.sub(r'\.+$', '', model)
                
                members.append({
                    "id": member_id,
                    "mac_address": mac_address,
                    "model": model,
                    "priority": int(priority),
                    "role": status,
                    "status": "active" if status != "missing" else "missing"
                })
    
    return {
        "members": len(members),
        "roles": [member["role"] for member in members],
        "member_details": members
    }

