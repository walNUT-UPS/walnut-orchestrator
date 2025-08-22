from __future__ import annotations

from typing import Any, Dict, Tuple
from utils.logging import get_logger

log = get_logger("parsers.snmp")


# OID constants
SYS_DESCR = "1.3.6.1.2.1.1.1.0"

# IF-MIB columns (ifTable: 1.3.6.1.2.1.2.2.1)
IF_TABLE = "1.3.6.1.2.1.2.2.1"
IF_INDEX = f"{IF_TABLE}.1"
IF_ADMIN_STATUS = f"{IF_TABLE}.7"
IF_OPER_STATUS = f"{IF_TABLE}.8"
IF_SPEED = f"{IF_TABLE}.5"
IF_ALIAS = f"{IF_TABLE}.2.1"  # note: not standard; alias is actually 1.3.6.1.2.1.31.1.1.1.18
IF_XTABLE_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"  # ifAlias in IF-MIB::ifXTable

# POWER-ETHERNET-MIB
PETH_MAIN_PSE_TABLE = "1.3.6.1.2.1.105.1.3.1"
PETH_PSE_PORT_TABLE = "1.3.6.1.2.1.105.1.1.1"

# LLDP-MIB
LLDP_REM_TABLE = "1.0.8802.1.1.2.1.4.1"

# ENTITY-MIB
ENT_PHYSICAL_TABLE = "1.3.6.1.2.1.47.1.1.1.1"


def _import_snmp():
    # Lazy import to keep module importable without deps installed
    from pysnmp.hlapi import (
        SnmpEngine,
        CommunityData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        getCmd,
        nextCmd,
    )

    return {
        "SnmpEngine": SnmpEngine,
        "CommunityData": CommunityData,
        "UdpTransportTarget": UdpTransportTarget,
        "ContextData": ContextData,
        "ObjectType": ObjectType,
        "ObjectIdentity": ObjectIdentity,
        "getCmd": getCmd,
        "nextCmd": nextCmd,
    }


def get_scalar(community: str, host: str, oid: str, port: int = 161, timeout: int = 5) -> Any:
    """Fetch a scalar OID value. Returns None on failure."""
    try:
        snmp = _import_snmp()
    except Exception as e:
        log.debug(f"pysnmp not available: {e}")
        return None
    try:
        iterator = snmp["getCmd"](
            snmp["SnmpEngine"](),
            snmp["CommunityData"](community, mpModel=1),
            snmp["UdpTransportTarget"]((host, port), timeout=timeout, retries=1),
            snmp["ContextData"](),
            snmp["ObjectType"](snmp["ObjectIdentity"](oid)),
        )
        errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
        if errorIndication or errorStatus:
            log.debug(f"SNMP get error: {errorIndication or errorStatus}")
            return None
        for name, val in varBinds:
            return val.prettyPrint()
        return None
    except Exception as e:
        log.debug(f"SNMP get exception: {e}")
        return None


def walk_table(
    community: str, host: str, base_oid: str, port: int = 161, timeout: int = 5
) -> Dict[int, Dict[str, Any]]:
    """
    Walk a table and return mapping of index -> {column_oid: value}.
    Keys are integer indexes where possible; values are pretty-printed.
    Returns empty dict on error.
    """
    try:
        snmp = _import_snmp()
    except Exception as e:
        log.debug(f"pysnmp not available: {e}")
        return {}
    rows: Dict[int, Dict[str, Any]] = {}
    try:
        for (errorIndication, errorStatus, errorIndex, varBinds) in snmp["nextCmd"](
            snmp["SnmpEngine"](),
            snmp["CommunityData"](community, mpModel=1),
            snmp["UdpTransportTarget"]((host, port), timeout=timeout, retries=1),
            snmp["ContextData"](),
            snmp["ObjectType"](snmp["ObjectIdentity"](base_oid)),
            lexicographicMode=False,
        ):
            if errorIndication or errorStatus:
                log.debug(f"SNMP walk error on {base_oid}: {errorIndication or errorStatus}")
                break
            for name, val in varBinds:
                oid_str = name.prettyPrint()
                if not oid_str.startswith(base_oid + "."):
                    continue
                suffix = oid_str[len(base_oid) + 1 :]
                # The last number(s) should be the index
                parts = suffix.split(".")
                index_str = parts[-1]
                try:
                    index = int(index_str)
                except Exception:
                    # fallback for composite indexes: try last part
                    try:
                        index = int(parts[-1])
                    except Exception:
                        continue
                rows.setdefault(index, {})[oid_str] = val.prettyPrint()
    except Exception as e:
        log.debug(f"SNMP walk exception on {base_oid}: {e}")
        return {}
    return rows


def map_if_and_poe(
    if_rows: Dict[int, Dict[str, Any]], poe_rows: Dict[int, Dict[str, Any]]
) -> Dict[int, Dict[str, Any]]:
    """Join IF-MIB rows with PoE rows by index if possible.
    If indexes don't align, mark poe_supported=False.
    """
    result: Dict[int, Dict[str, Any]] = {}
    for ifidx, cols in if_rows.items():
        merged = dict(cols)
        poe = poe_rows.get(ifidx)
        if poe:
            merged["poe_supported"] = True
            merged["poe_row"] = poe
        else:
            merged["poe_supported"] = False
        result[ifidx] = merged
    return result

