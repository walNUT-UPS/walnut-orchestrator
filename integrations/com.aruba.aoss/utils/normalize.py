from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Tuple
import re


DEFAULT_MEMBER = 1
DEFAULT_SLOT_FIXED = "1"  # fixed-port models
SLOT_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_PORTS_PER_SLOT = 48  # conservative default for range expansion across slots


@dataclass(frozen=True)
class PortKey:
    member: int   # default 1 if omitted
    slot: str     # 'A'..'Z' or '1' for fixed-port models
    port: int


def _parse_int(s: str, default: int | None = None) -> int | None:
    try:
        return int(s)
    except Exception:
        return default


def parse_interface_id(s: str) -> PortKey:
    """
    Accepts: 'A1', 'C23', '1/1/24', '2/B4', '24'
    Returns PortKey(member, slot, port). Heuristics:
      - If letter+number: slot is that letter, member defaults to 1
      - If three-part 1/1/24: member/slot/port with slot numeric '1' for fixed
      - If two-part 1/48 or 1/1-1/48 forms: treat as member/port on fixed, slot='1'
      - If plain number '24': member=1, slot='1'
    """
    s = s.strip()
    # 2/B4 form
    m = re.fullmatch(r"(?P<member>\d+)\/(?P<slot>[A-Za-z])(?P<port>\d+)", s)
    if m:
        return PortKey(int(m.group("member")), m.group("slot").upper(), int(m.group("port")))

    # 1/1/24 form
    m = re.fullmatch(r"(?P<member>\d+)\/(?P<slot>\d+)\/(?P<port>\d+)", s)
    if m:
        return PortKey(int(m.group("member")), m.group("slot"), int(m.group("port")))

    # 1/24 or 1/1 form (fixed port)
    m = re.fullmatch(r"(?P<member>\d+)\/(?P<port>\d+)", s)
    if m:
        return PortKey(int(m.group("member")), DEFAULT_SLOT_FIXED, int(m.group("port")))

    # A1 form
    m = re.fullmatch(r"(?P<slot>[A-Za-z])(?P<port>\d+)", s)
    if m:
        return PortKey(DEFAULT_MEMBER, m.group("slot").upper(), int(m.group("port")))

    # plain port number
    m = re.fullmatch(r"(?P<port>\d+)", s)
    if m:
        return PortKey(DEFAULT_MEMBER, DEFAULT_SLOT_FIXED, int(m.group("port")))

    raise ValueError(f"Unsupported interface id: {s}")


def _slot_range(start: str, end: str) -> List[str]:
    if start == end:
        return [start]
    if start.isdigit() and end.isdigit():
        # numeric slots (fixed models should not range across slots; handle anyway)
        a, b = int(start), int(end)
        step = 1 if a <= b else -1
        return [str(i) for i in range(a, b + step, step)]
    # letters
    start_i = SLOT_LETTERS.index(start.upper())
    end_i = SLOT_LETTERS.index(end.upper())
    step = 1 if start_i <= end_i else -1
    return [SLOT_LETTERS[i] for i in range(start_i, end_i + step, step)]


def expand_range(expr: str) -> list[PortKey]:
    """
    Accepts compressed expressions:
      'A1-A24', '1/1/1-1/1/10', '2/B4-2/B5', '1/1-1/48', '1/A1-1/B4'
    and returns a flat, ordered list of PortKey.
    """
    expr = expr.strip()
    if '-' not in expr:
        return [parse_interface_id(expr)]

    left, right = expr.split('-', 1)
    s = parse_interface_id(left)
    e = parse_interface_id(right)

    if s.member != e.member:
        # split by member; expand separately then concatenate in order
        first = f"{s.member}/{s.slot}{s.port}"
        second = f"{e.member}/{e.slot}{e.port}"
        expanded = []
        expanded.extend(expand_range(f"{first}-{s.member}/{e.slot}{e.port}")) if s.member == e.member else expanded.extend([s])
        expanded.extend(expand_range(second))
        return sorted(expanded, key=lambda k: (k.member, str(k.slot), k.port))

    # Same member: handle same slot or across slots
    if s.slot == e.slot:
        step = 1 if s.port <= e.port else -1
        return [PortKey(s.member, s.slot, p) for p in range(s.port, e.port + step, step)]

    result: list[PortKey] = []
    for slot in _slot_range(s.slot, e.slot):
        if slot == s.slot:
            start_port = s.port
            end_port = MAX_PORTS_PER_SLOT
        elif slot == e.slot:
            start_port = 1
            end_port = e.port
        else:
            start_port = 1
            end_port = MAX_PORTS_PER_SLOT
        for p in range(start_port, end_port + 1):
            result.append(PortKey(s.member, slot, p))
    return result


def compress_to_cli(port_keys: list[PortKey]) -> list[str]:
    """
    Group by (member, slot) and compress sequential ports into ranges:
      [(1,'A',1), (1,'A',2), (1,'A',3), (1,'B',1)] -> ['1/A1-1/A3','1/B1']
    For fixed-port models use '1/1/1-1/1/10' form.
    """
    if not port_keys:
        return []
    # group by member, slot
    groups: dict[Tuple[int, str], List[int]] = {}
    for k in sorted(port_keys, key=lambda x: (x.member, str(x.slot), x.port)):
        groups.setdefault((k.member, k.slot), []).append(k.port)

    result: list[str] = []
    for (member, slot), ports in groups.items():
        ports = sorted(set(ports))
        start = prev = ports[0]
        def _emit(a: int, b: int) -> None:
            if slot.isdigit():
                if a == b:
                    result.append(f"{member}/{slot}/{a}")
                else:
                    result.append(f"{member}/{slot}/{a}-{member}/{slot}/{b}")
            else:
                if a == b:
                    result.append(f"{member}/{slot}{a}")
                else:
                    result.append(f"{member}/{slot}{a}-{member}/{slot}{b}")
        for p in ports[1:]:
            if p == prev + 1:
                prev = p
            else:
                _emit(start, prev)
                start = prev = p
        _emit(start, prev)
    return result


def is_protected_port(lldp_row: dict | None, poe_draw: float | None) -> bool:
    """Heuristic: protect uplinks/stack ports.
    - If LLDP neighbor capability indicates 'bridge', 'switch', 'router' -> protected.
    - If PoE draw is very low (<0.5W), not protected based on power alone.
    - If LLDP absent, fall back to False.
    """
    if lldp_row:
        text = " ".join(str(v).lower() for v in lldp_row.values())
        for kw in ("bridge", "switch", "router", "mac bridge", "stack"):  # common LLDP strings
            if kw in text:
                return True
    if poe_draw is not None and poe_draw < 0.5:
        return False
    return False


def _iter_target_ids(target: dict) -> Iterable[str]:
    # Accept shapes:
    # {"poe-port":{"ids":[...]}}, or {"switch":"...","children":[{"interface":"..."}]}
    if not target:
        return []
    if "poe-port" in target and isinstance(target["poe-port"], dict):
        ids = target["poe-port"].get("ids", [])
        for i in ids:
            yield str(i)
    elif "children" in target and isinstance(target["children"], list):
        for child in target["children"]:
            iface = child.get("interface") if isinstance(child, dict) else None
            if iface:
                yield str(iface)


def normalize_targets(target: dict) -> list[PortKey]:
    keys: list[PortKey] = []
    for token in _iter_target_ids(target):
        token = token.strip()
        if '-' in token:
            keys.extend(expand_range(token))
        else:
            keys.append(parse_interface_id(token))
    # dedupe preserving order
    seen = set()
    uniq: list[PortKey] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    return uniq

