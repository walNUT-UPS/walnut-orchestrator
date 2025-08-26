from __future__ import annotations

import time
import logging
import re
from typing import Any, Dict, List, Optional
import re

# Use standard logging instead of relative imports for better compatibility
log = logging.getLogger("com.aruba.aoss.driver")

# Import helper modules with absolute paths to avoid relative import issues
import os
import sys
integration_path = os.path.dirname(__file__)
if integration_path not in sys.path:
    sys.path.insert(0, integration_path)

from utils.normalize import (
    PortKey,
    compress_to_cli,
    normalize_targets,
    is_protected_port,
)
from parsers.interfaces import parse_show_modules, parse_show_version, parse_show_vsf, parse_show_stack
from parsers import snmp as snmp_helpers

# Module-level cache for SSH inventory throttling
_SSH_PORTS_CACHE: Dict[int, Dict[str, Any]] = {}


class SSH:
    """Minimal Netmiko wrapper with context management."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        device_type: str,
        port: int = 22,
        secret: Optional[str] = None,
        timeout: int = 30,
    ) -> None:
        self.kw = dict(
            host=host,
            username=username,
            password=password,
            device_type=device_type,
            port=port,
            timeout=timeout,
        )
        self.secret = secret
        self.conn = None

    def __enter__(self):
        try:
            from netmiko import ConnectHandler
        except Exception as e:
            raise RuntimeError(f"netmiko not available: {e}")
        self.conn = ConnectHandler(**self.kw)
        if self.secret:
            try:
                self.conn.enable()
            except Exception:
                pass
        try:
            self.conn.send_command("no page", expect_string=None)
        except Exception:
            # some models use 'terminal length 1000'
            try:
                self.conn.send_command("terminal length 1000", expect_string=None)
            except Exception:
                pass
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.conn:
                self.conn.disconnect()
        except Exception:
            pass


def _snmp_ctx(connection: dict) -> dict:
    return dict(
        community=connection.get("snmp_community", "public"),
        host=connection.get("snmp_host") or connection.get("hostname"),
        port=int(connection.get("snmp_port", 161)),
        timeout=int(connection.get("timeout_s", 5)),
    )


def _ssh_ctx(connection: dict) -> dict:
    return dict(
        host=connection.get("hostname"),
        username=connection.get("username"),
        password=connection.get("password"),
        device_type=connection.get("device_type", "aruba_osswitch"),
        port=int(connection.get("ssh_port", 22)),
        secret=connection.get("enable_password") or None,
        timeout=int(connection.get("timeout_s", 30)),
    )


def _safe_snmp_get(oid: str, ctx: dict) -> Any:
    try:
        return snmp_helpers.get_scalar(ctx["community"], ctx["host"], oid, ctx["port"], ctx["timeout"])
    except Exception as e:
        log.debug(f"SNMP get failed: {e}")
        return None


def _safe_snmp_walk(base_oid: str, ctx: dict) -> Dict[int, Dict[str, Any]]:
    try:
        return snmp_helpers.walk_table(ctx["community"], ctx["host"], base_oid, ctx["port"], ctx["timeout"])
    except Exception as e:
        log.debug(f"SNMP walk failed: {e}")
        return {}


def _ssh_probe(connection: dict) -> Dict[str, Any]:
    ok = False
    version = {}
    vsf = {}
    modules = []
    try:
        with SSH(**_ssh_ctx(connection)) as conn:
            out = conn.send_command("show version", expect_string=None)
            version = parse_show_version(out)
            try:
                out_vsf = conn.send_command("show vsf", expect_string=None)
                vsf = parse_show_vsf(out_vsf)
            except Exception:
                vsf = {}
            try:
                out_mod = conn.send_command("show modules", expect_string=None)
                modules = parse_show_modules(out_mod)
            except Exception:
                modules = []
            # enter/exit config mode quickly to verify
            try:
                conn.config_mode()
                conn.exit_config_mode()
            except Exception:
                pass
            ok = True
    except Exception as e:
        log.debug(f"SSH probe failed: {e}")
    return {"ok": ok, "version": version, "vsf": vsf, "slots": modules}


def test_connection(connection: dict) -> dict:
    start = time.time()
    snmp = _snmp_ctx(connection)
    sysdescr = _safe_snmp_get(snmp_helpers.SYS_DESCR, snmp)
    poe_walk = _safe_snmp_walk(snmp_helpers.PETH_MAIN_PSE_TABLE, snmp)
    snmp_ok = bool(sysdescr or poe_walk)

    ssh_probe = _ssh_probe(connection)
    ssh_ok = ssh_probe.get("ok", False)

    topo_type = "standalone"
    topo_members = 1
    topo_slots: List[str] = []
    if ssh_probe.get("vsf", {}).get("members", 0) > 1:
        topo_type = "vsf"
        topo_members = ssh_probe["vsf"]["members"]
    elif ssh_probe.get("slots"):
        topo_type = "chassis"
        topo_slots = ssh_probe["slots"]

    duration_ms = int((time.time() - start) * 1000)
    result = {
        "ok": bool(snmp_ok or ssh_ok),
        "device": {
            "model": ssh_probe.get("version", {}).get("model", "unknown"),
            "os_version": ssh_probe.get("version", {}).get("version", "unknown"),
            "serial": ssh_probe.get("version", {}).get("serial", "unknown"),
        },
        "topology": {
            "type": topo_type,
            "members": topo_members if topo_type == "vsf" else None,
            "slots": topo_slots if topo_type == "chassis" else None,
        },
        "poe_supported": bool(poe_walk),
        "snmp_ok": snmp_ok,
        "ssh_ok": ssh_ok,
        "latency_ms": duration_ms,
    }
    return result


def heartbeat(connection: dict) -> dict:
    start = time.time()
    snmp = _snmp_ctx(connection)
    poe = _safe_snmp_walk(snmp_helpers.PETH_MAIN_PSE_TABLE, snmp)
    state = "connected" if poe else "degraded" if _safe_snmp_get(snmp_helpers.SYS_DESCR, snmp) else "error"
    duration_ms = int((time.time() - start) * 1000)
    snapshot = {"poe": poe}
    return {"state": state, "latency_ms": duration_ms, "snapshot": snapshot}


def discover(connection: dict) -> dict:
    snmp = _snmp_ctx(connection)
    if_rows = _safe_snmp_walk(snmp_helpers.IF_TABLE, snmp)
    if_alias = _safe_snmp_walk(snmp_helpers.IF_XTABLE_ALIAS, snmp)
    poe_port = _safe_snmp_walk(snmp_helpers.PETH_PSE_PORT_TABLE, snmp)
    lldp = _safe_snmp_walk(snmp_helpers.LLDP_REM_TABLE, snmp)
    entity = _safe_snmp_walk(snmp_helpers.ENT_PHYSICAL_TABLE, snmp)

    # merge if_table + aliases
    for idx, row in if_rows.items():
        alias = None
        # ifXTable alias rows may be indexed by ifIndex
        if idx in if_alias:
            for _, v in if_alias[idx].items():
                alias = v
                break
        if alias:
            row["ifAlias"] = alias

    merged = snmp_helpers.map_if_and_poe(if_rows, poe_port)

    interfaces = []
    for ifidx, row in merged.items():
        draw_w = None
        priority = None
        poe_row = row.get("poe_row")
        if poe_row:
            # heuristic columns (vendor-specific); leave as strings if unknown
            # A few Aruba OIDs under pethPsePortTable.* may include power and priority.
            for k, v in poe_row.items():
                ks = str(k)
                if ks.endswith(".6." + str(ifidx)) or "Power" in ks:
                    try:
                        draw_w = float(v)
                    except Exception:
                        pass
                if "priority" in ks.lower():
                    priority = v
        iface = {
            "id": str(ifidx),
            "member": 1,
            "slot": "1",
            "port": ifidx,
            "admin": row.get(snmp_helpers.IF_ADMIN_STATUS, "unknown"),
            "oper": row.get(snmp_helpers.IF_OPER_STATUS, "unknown"),
            "speed": row.get(snmp_helpers.IF_SPEED, None),
            "poe_draw_w": draw_w,
            "priority": priority,
            "labels": {},
        }
        # attach LLDP neighbor hint
        if ifidx in lldp:
            iface["labels"]["lldp"] = lldp[ifidx]
        interfaces.append(iface)

    inv = {
        "switch": {
            "attrs": {
                "sysDescr": _safe_snmp_get(snmp_helpers.SYS_DESCR, snmp),
            },
            "children": {
                "interfaces": interfaces,
                "psus": [entity.get(i, {}) for i in sorted(entity.keys()) if any("Power" in str(k) for k in entity.get(i, {}).keys())],
                "fans": [entity.get(i, {}) for i in sorted(entity.keys()) if any("Fan" in str(k) for k in entity.get(i, {}).keys())],
                "slots": [entity.get(i, {}) for i in sorted(entity.keys()) if any("Slot" in str(k) or "chassis" in str(k).lower() for k in entity.get(i, {}).keys())],
            },
        }
    }
    return inv


def _build_plan(
    capability: str,
    target: dict,
    params: dict,
    connection: dict,
    ranges: List[str],
    preconditions: Optional[List[dict]] = None,
    effects: Optional[dict] = None,
) -> dict:
    plan_cli: List[str] = ["configure"]
    for r in ranges:
        plan_cli.append(f"interface {r}")
        if capability == "poe.port:set":
            state = params.get("state")
            if state == "off":
                plan_cli.append("no power-over-ethernet")
            elif state == "on":
                plan_cli.append("power-over-ethernet")
            elif state == "cycle":
                plan_cli.append("no power-over-ethernet")
                plan_cli.append("! client-side wait 4s, then re-enable")
                plan_cli.append("power-over-ethernet")
        elif capability == "poe.priority:set":
            level = params.get("level", "low")
            plan_cli.append(f"power-over-ethernet {level}")
        elif capability == "net.interface:set":
            admin = params.get("admin", "up")
            plan_cli.append("enable" if admin == "up" else "disable")
        plan_cli.append("exit")
    plan_cli.append("exit")
    return {
        "dry_run": True,
        "capability": capability,
        "target": target,
        "params": params,
        "preconditions": preconditions or [],
        "plan_cli": plan_cli,
        "effects": effects or {},
        "risk": "low",
        "notes": ["ranges compressed per slot/member"],
    }


def _validate_confirm(params: dict, require: bool) -> Optional[dict]:
    if require and not params.get("confirm"):
        return {"ok": False, "error_code": "validation_error", "error": "Operation requires confirm=true"}
    return None


def _do_config(connection: dict, lines: List[str]) -> List[str]:
    outputs: List[str] = []
    with SSH(**_ssh_ctx(connection)) as conn:
        outputs = conn.send_config_set(lines)
    return outputs if isinstance(outputs, list) else [str(outputs)]


def _poe_port_set(target: dict, params: dict, connection: dict, dry_run: bool) -> dict:
    state = params.get("state")
    if state not in ("on", "off", "cycle"):
        return {"ok": False, "error_code": "validation_error", "error": "state must be one of on|off|cycle"}
    
    # destructive ops require confirm
    if (state in ("off", "cycle")) and not dry_run:
        val = _validate_confirm(params, True)
        if val:
            return val
    
    keys = normalize_targets(target)
    ranges = compress_to_cli(keys)

    if dry_run:
        return _poe_port_set_dry_run(state, keys, ranges, connection)

    # execute
    lines: List[str] = ["interface " + r for r in ranges]
    if state == "off":
        lines.append("no power-over-ethernet")
    elif state == "on":
        lines.append("power-over-ethernet")
    elif state == "cycle":
        lines.append("no power-over-ethernet")
    lines.append("exit")
    out = _do_config(connection, ["configure"] + lines + (["exit"] if lines[-1] != "exit" else []))
    if state == "cycle":
        time.sleep(4)
        out2 = _do_config(connection, ["configure", *("interface " + r for r in ranges), "power-over-ethernet", "exit", "exit"])
        out.extend(out2)
    return {"ok": True, "result": out}


def _poe_port_set_dry_run(state: str, keys: List[PortKey], ranges: List[str], connection: dict) -> dict:
    """Standardized dry-run response for PoE port operations."""
    try:
        # Check preconditions
        snmp = _snmp_ctx(connection)
        poe_main = _safe_snmp_walk(snmp_helpers.PETH_MAIN_PSE_TABLE, snmp)
        poe_supported = bool(poe_main)
        
        # Check protected ports
        protected: List[str] = []
        for k in keys:
            if is_protected_port(None, None):
                protected.append(f"{k.member}/{k.slot}{k.port}")
        
        preconditions = [
            {"check": "poe_supported", "ok": poe_supported},
            {"check": "protected_ports", "ok": len(protected) == 0, "details": {"blocked": protected}},
        ]
        
        # Determine severity
        if not poe_supported:
            severity = "error"
            reason = "PoE not supported on this device"
        elif protected:
            severity = "error" 
            reason = f"Cannot modify protected ports: {', '.join(protected)}"
        else:
            severity = "warn"  # PoE operations are potentially disruptive
            reason = "inventory stale; fast refresh failed" if not poe_main else None

        # Build CLI plan
        cli_commands = ["configure"]
        for r in ranges:
            cli_commands.append(f"interface {r}")
            if state == "off":
                cli_commands.append("no power-over-ethernet")
            elif state == "on":
                cli_commands.append("power-over-ethernet")
            elif state == "cycle":
                cli_commands.append("no power-over-ethernet")
                cli_commands.append("! wait 4s")
                cli_commands.append("power-over-ethernet")
            cli_commands.append("exit")
        cli_commands.append("exit")

        # Build effects
        per_target_effects = []
        for k in keys:
            port_id = f"{k.member}/{k.slot}{k.port}" if not k.slot.isdigit() else f"{k.member}/{k.slot}/{k.port}"
            per_target_effects.append({
                "id": port_id,
                "from": {"draw_w": 7.5},
                "to": {"draw_w": 0.0 if state in ("off", "cycle") else 7.5}
            })

        # Build target range string for idempotency key
        target_range = ",".join(ranges)

        return {
            "ok": poe_supported and not protected,
            "severity": severity,
            "idempotency_key": f"aoss.poe.port:set:{target_range}:{state}",
            "preconditions": preconditions,
            "plan": {
                "kind": "cli",
                "preview": cli_commands
            },
            "effects": {
                "summary": f"Ports {target_range} would power {'off' if state == 'off' else 'on' if state == 'on' else 'cycle'}",
                "per_target": per_target_effects
            },
            "reason": reason
        }
        
    except Exception as e:
        return {
            "ok": False,
            "severity": "error",
            "idempotency_key": f"aoss.poe.port:set:error",
            "preconditions": [{"check": "connectivity", "ok": False}],
            "plan": {"kind": "cli", "preview": []},
            "effects": {"summary": "Operation failed", "per_target": []},
            "reason": f"Dry-run check failed: {str(e)}"
        }


def _poe_priority_set(target: dict, params: dict, connection: dict, dry_run: bool) -> dict:
    level = params.get("level")
    if level not in ("low", "high", "critical"):
        return {"ok": False, "error_code": "validation_error", "error": "level must be low|high|critical"}

    keys = normalize_targets(target)
    ranges = compress_to_cli(keys)
    pre = [{"check": "poe_supported", "ok": True}]
    plan = _build_plan("poe.priority:set", target, params, connection, ranges, pre, effects={})
    if dry_run:
        return plan
    lines = ["configure"]
    for r in ranges:
        lines += [f"interface {r}", f"power-over-ethernet {level}", "exit"]
    lines.append("exit")
    out = _do_config(connection, lines)
    return {"ok": True, "result": out}


def _net_interface_set(target: dict, params: dict, connection: dict, dry_run: bool) -> dict:
    admin = params.get("admin")
    if admin not in ("up", "down"):
        return {"ok": False, "error_code": "validation_error", "error": "admin must be up|down"}
    keys = normalize_targets(target)
    ranges = compress_to_cli(keys)
    plan = _build_plan("net.interface:set", target, params, connection, ranges, effects={})
    if dry_run:
        return plan
    lines = ["configure"]
    for r in ranges:
        lines += [f"interface {r}", ("enable" if admin == "up" else "disable"), "exit"]
    lines.append("exit")
    out = _do_config(connection, lines)
    return {"ok": True, "result": out}


def _switch_inventory(connection: dict) -> dict:
    # Use discover() for detailed; provide minimal here
    try:
        inv = discover(connection)
        return inv
    except Exception as e:
        return {"error": str(e), "error_code": "unknown"}


def _switch_health(connection: dict) -> dict:
    hb = heartbeat(connection)
    return hb


def _poe_status(connection: dict) -> dict:
    snmp = _snmp_ctx(connection)
    main = _safe_snmp_walk(snmp_helpers.PETH_MAIN_PSE_TABLE, snmp)
    ports = _safe_snmp_walk(snmp_helpers.PETH_PSE_PORT_TABLE, snmp)
    return {"main": main, "ports": ports}


def _switch_config(verb: str, connection: dict, dry_run: bool) -> dict:
    if verb == "save":
        plan = {
            "dry_run": True,
            "capability": "switch.config:save",
            "plan_cli": ["write memory"],
        }
        if dry_run:
            return plan
        with SSH(**_ssh_ctx(connection)) as conn:
            out = conn.send_command("write memory", expect_string=None)
        return {"ok": True, "result": out}
    elif verb == "backup":
        plan = {
            "dry_run": True,
            "capability": "switch.config:backup",
            "plan_cli": ["show running-config"],
        }
        if dry_run:
            return plan
        with SSH(**_ssh_ctx(connection)) as conn:
            out = conn.send_command("show running-config", expect_string=None)
        return {"ok": True, "text": out}
    else:
        return {"ok": False, "error_code": "validation_error", "error": f"Unsupported verb {verb}"}


def _switch_reboot(params: dict, connection: dict, dry_run: bool) -> dict:
    need = _validate_confirm(params, True)
    if need:
        return need
    plan = {
        "dry_run": True,
        "capability": "switch.reboot:exec",
        "plan_cli": ["reload", "y"],
    }
    if dry_run:
        return plan
    with SSH(**_ssh_ctx(connection)) as conn:
        conn.send_command_timing("reload")
        conn.send_command_timing("y")
    return {"ok": True}


def execute(
    capability_id: str,
    verb: str,
    target: dict,
    params: dict,
    connection: dict,
    dry_run: bool = False,
) -> dict:
    try:
        if capability_id == "switch.inventory" and verb == "read":
            return _switch_inventory(connection)
        if capability_id == "switch.health" and verb == "read":
            return _switch_health(connection)
        if capability_id == "poe.status" and verb == "read":
            return _poe_status(connection)
        if capability_id == "poe.port" and verb == "set":
            return _poe_port_set(target, params or {}, connection, dry_run)
        if capability_id == "poe.priority" and verb == "set":
            return _poe_priority_set(target, params or {}, connection, dry_run)
        if capability_id == "net.interface" and verb == "set":
            return _net_interface_set(target, params or {}, connection, dry_run)
        if capability_id == "switch.config" and verb in ("save", "backup"):
            return _switch_config(verb, connection, dry_run)
        if capability_id == "switch.reboot" and verb == "exec":
            return _switch_reboot(params or {}, connection, dry_run)
        return {"ok": False, "error_code": "validation_error", "error": "Unsupported capability/verb"}
    except Exception as e:
        log.debug(f"execute error: {e}")
        return {"ok": False, "error_code": "unknown", "error": str(e)}


def _latency_probe(connection: dict) -> int:
    start = time.time()
    _ = _snmp_ctx(connection)  # access only
    return int((time.time() - start) * 1000)


def _get_stack_info(connection: dict) -> dict:
    """Get stack member information via SSH using both 'show stack' and 'show vsf' commands."""
    log.info(f"Attempting to connect to {connection['hostname']} for stack info")
    try:
        # Use SSH to query stack status
        with SSH(
            host=connection["hostname"],
            username=connection["username"], 
            password=connection["password"],
            device_type=connection.get("device_type", "aruba_osswitch"),
            port=connection.get("ssh_port", 22),
            secret=connection.get("enable_password"),
            timeout=connection.get("timeout_s", 30),
        ) as ssh_conn:
            
            log.info("SSH connection established successfully")
            members = []
            
            # Try 'show stack' first (more common on newer Aruba switches)
            try:
                log.info("Executing 'show stack' command")
                stack_output = ssh_conn.send_command("show stack")
                log.info(f"'show stack' output ({len(stack_output)} chars): {stack_output[:200]}...")
                
                if "Invalid input" not in stack_output and "Unknown command" not in stack_output:
                    stack_info = parse_show_stack(stack_output)
                    log.info(f"Parsed stack info: {stack_info}")
                    
                    # Use detailed member information from show stack
                    for member_detail in stack_info.get("member_details", []):
                        members.append({
                            "id": member_detail["id"],
                            "model": member_detail["model"],
                            "status": member_detail["status"],
                            "priority": member_detail.get("priority"),
                            "role": member_detail["role"],
                            "mac_address": member_detail.get("mac_address"),
                        })
                    
                    if members:  # If we found stack members, return them
                        log.info(f"Found {len(members)} stack members via 'show stack'")
                        return {"members": members}
                else:
                    log.info("'show stack' command returned invalid/unknown response")
            except Exception as e:
                log.warning(f"'show stack' command failed: {e}")
            
            # Fall back to 'show vsf' if 'show stack' didn't work
            try:
                log.info("Executing 'show vsf' command")
                vsf_output = ssh_conn.send_command("show vsf")
                log.info(f"'show vsf' output ({len(vsf_output)} chars): {vsf_output[:200]}...")
                
                if "Invalid input" not in vsf_output and "Unknown command" not in vsf_output:
                    vsf_info = parse_show_vsf(vsf_output)
                    log.info(f"Parsed VSF info: {vsf_info}")
                    
                    # Create member entries from VSF output (less detailed)
                    if vsf_info.get("members", 0) > 0:
                        for i in range(1, vsf_info["members"] + 1):
                            role = "member"
                            if i <= len(vsf_info.get("roles", [])):
                                role = vsf_info["roles"][i-1]
                            
                            members.append({
                                "id": str(i),
                                "model": "Unknown",  # VSF output doesn't provide model details
                                "status": "active",   # VSF members are typically active if detected
                                "priority": None,
                                "role": role,
                            })
                        
                        log.info(f"Found {len(members)} stack members via 'show vsf'")
                        return {"members": members}
                else:
                    log.info("'show vsf' command returned invalid/unknown response")
            except Exception as e:
                log.warning(f"'show vsf' command failed: {e}")
            
            # If both commands failed or returned no members, return empty
            log.info("No stack members found via either command")
            return {"members": []}
            
    except Exception as e:
        log.error(f"SSH connection to {connection['hostname']} failed: {e}")
        # Return empty list for non-stacked switches or connection errors
        return {"members": []}


def _get_port_info(connection: dict) -> dict:
    """Get real port information via SNMP.
    
    Queries IF-MIB (ifTable, ifXTable), POWER-ETHERNET-MIB, and returns
    a normalized list of port dicts.
    """
    try:
        snmp = _snmp_ctx(connection)
        if_rows = _safe_snmp_walk(snmp_helpers.IF_TABLE, snmp)
        alias_rows = _safe_snmp_walk(snmp_helpers.IF_XTABLE_ALIAS, snmp)
        poe_rows = _safe_snmp_walk(snmp_helpers.PETH_PSE_PORT_TABLE, snmp)
        if_high_rows = _safe_snmp_walk("1.3.6.1.2.1.31.1.1.1.15", snmp)

        ports: List[Dict[str, Any]] = []
        for ifidx, cols in if_rows.items():
            port: Dict[str, Any] = {"port_id": str(ifidx)}

            # ifDescr
            for k, v in cols.items():
                if k.endswith(f".2.{ifidx}"):
                    port["description"] = v
                    break

            # Alias (ifXTable)
            if ifidx in alias_rows:
                try:
                    port["alias"] = next(iter(alias_rows[ifidx].values()))
                except Exception:
                    port["alias"] = None

            # ifAdmin/ifOper
            for k, v in cols.items():
                if k.endswith(f".7.{ifidx}"):
                    port["if_admin"] = v
                if k.endswith(f".8.{ifidx}"):
                    port["if_oper"] = v

            # ifType
            for k, v in cols.items():
                if k.endswith(f".3.{ifidx}"):
                    port["if_type"] = v
                    break

            # ifSpeed
            for k, v in cols.items():
                if k.endswith(f".5.{ifidx}"):
                    port["speed"] = v
                    break

            # ifHighSpeed
            if ifidx in if_high_rows:
                try:
                    port["if_high_speed"] = next(iter(if_high_rows[ifidx].values()))
                except Exception:
                    pass

            # PoE (best-effort)
            if ifidx in poe_rows:
                poe_values = poe_rows[ifidx]
                port["poe_supported"] = True
                for pk, pv in poe_values.items():
                    lpk = str(pk).lower()
                    if "power" in lpk:
                        try:
                            port["poe_power"] = float(pv)
                        except Exception:
                            port["poe_power"] = pv
                    if "class" in lpk:
                        port["poe_class"] = pv
            else:
                port["poe_supported"] = False

            ports.append(port)

        try:
            log.info(
                "AOSS IF-MIB rows=%d ifXTable=%d poe=%d ifHighSpeed=%d composed_ports=%d",
                len(if_rows), len(alias_rows), len(poe_rows), len(if_high_rows), len(ports)
            )
        except Exception:
            pass
        # If SNMP yielded nothing, attempt SSH fallback to get a minimal view
        if len(ports) == 0:
            try:
                ports = _ssh_ports_fallback(connection)
                if ports:
                    log.info("AOSS SSH fallback returned %d ports", len(ports))
            except Exception as e:
                log.warning("SSH fallback failed: %s", e)
        return {"ports": ports}
    except Exception as e:
        return {"ports": [], "error": str(e)}


def _ssh_ports_fallback(connection: dict) -> List[Dict[str, Any]]:
    """Best-effort SSH fallback to list ports when SNMP is unavailable.

    Parses 'show interfaces brief' output. Returns a list of minimal port dicts:
    { port_id, description?, alias?, if_oper, speed?, if_type? }.
    """
    out = ""
    with SSH(**_ssh_ctx(connection)) as conn:
        try:
            out = conn.send_command("show interfaces brief", expect_string=None)
        except Exception:
            # Some platforms use 'show interfaces status'
            out = conn.send_command("show interfaces status", expect_string=None)

    ports: List[Dict[str, Any]] = []
    for line in out.splitlines():
        line = line.strip()
        # Skip headers and separators
        if (not line) or line.startswith("Status and Counters") or line.startswith("Port ") or line.startswith("-"):
            continue
        # The brief table has a '|' column: left = "<port> <type>", right = columns
        left, sep, right = line.partition('|')
        left = left.rstrip()
        right = right.strip()
        # Extract port id and type
        lparts = left.split()
        if not lparts:
            continue
        raw_id = lparts[0]
        # Some IDs have -Trk suffix and/or trailing *
        pid = re.sub(r"-.*$", "", raw_id).rstrip('*')
        type_str = lparts[1] if len(lparts) > 1 else ''
        # Parse status and mode/speed from right columns
        status = "unknown"
        speed_mbps = None
        if right:
            rparts = right.split()
            # rparts: [No, Yes, Up, 1000FDx, ...] or similar
            if len(rparts) >= 3:
                st = rparts[2].lower()
                status = 'up' if 'up' in st else ('down' if 'down' in st else 'unknown')
            if len(rparts) >= 4:
                mode = rparts[3]
                # Map 1000FDx / 100FDx / 10GigFD to Mbps
                m = re.match(r"(?i)(\d+)(gig)?(fdx|hdx)?", mode)
                if m:
                    try:
                        val = int(m.group(1))
                        if m.group(2):  # 'gig'
                            val *= 1000
                        speed_mbps = val
                    except Exception:
                        speed_mbps = None
        # Map media from type string if possible
        media = _infer_media_from_type(type_str)
        ports.append({
            "port_id": pid,
            "description": None,
            "alias": None,
            "if_oper": status,
            "if_high_speed": speed_mbps,
            "if_type": None,
            "_media_hint": media,
        })
    return ports


def _ssh_ports_fallback_throttled(instance_id: int, connection: dict, min_interval_s: int) -> List[Dict[str, Any]]:
    """Throttle SSH polling using a module-level cache keyed by instance_id."""
    now = time.time()
    cache = _SSH_PORTS_CACHE.get(instance_id)
    if cache and (now - cache.get("ts", 0) < max(60, min_interval_s)):
        return cache.get("ports", [])
    ports = _ssh_ports_fallback(connection)
    _SSH_PORTS_CACHE[instance_id] = {"ts": now, "ports": ports}
    return ports


def _ssh_lldp_neighbors_throttled(instance_id: int, connection: dict, min_interval_s: int) -> Dict[str, Dict[str, Any]]:
    now = time.time()
    cache = _SSH_PORTS_CACHE.get(instance_id)
    if cache and (now - cache.get("ts_lldp", 0) < max(60, min_interval_s)):
        return cache.get("lldp", {})
    data = _ssh_lldp_neighbors(connection)
    if cache is None:
        _SSH_PORTS_CACHE[instance_id] = {"ts_lldp": now, "lldp": data}
    else:
        cache["ts_lldp"] = now
        cache["lldp"] = data
    return data


def _ssh_lldp_neighbors(connection: dict) -> Dict[str, Dict[str, Any]]:
    """Parse LLDP neighbors via 'show lldp info remote-device'.

    Returns mapping: local_port_id -> { chassis_id, port_id, port_descr, sys_name }
    """
    out = ""
    with SSH(**_ssh_ctx(connection)) as conn:
        out = conn.send_command("show lldp info remote-device", expect_string=None)

    nbrs: Dict[str, Dict[str, Any]] = {}
    in_table = False
    for line in out.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("LLDP Remote Devices Information"):
            in_table = True
            continue
        if not in_table:
            continue
        # Skip header and separator
        if line.strip().startswith("LocalPort") or set(line.strip()) == {"-"} or line.strip().startswith("-"):
            continue
        # Expect 'LocalPort | ChassisId  PortId  PortDescr SysName'
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 2:
            continue
        local = parts[0].split()[0] if parts[0] else None
        right = parts[1]
        if not local or not right:
            continue
        # Split right into columns by 2+ spaces
        cols = [c.strip() for c in re.split(r"\s{2,}", right) if c.strip()]
        chassis = cols[0] if len(cols) > 0 else None
        port_id = cols[1] if len(cols) > 1 else None
        port_descr = cols[2] if len(cols) > 2 else None
        sys_name = cols[3] if len(cols) > 3 else None
        # Normalize local port to match inventory
        local_norm = re.sub(r"-.*$", "", local).rstrip('*')
        nbrs[local_norm] = {
            "chassis_id": chassis,
            "port_id": port_id,
            "port_descr": port_descr,
            "sys_name": sys_name,
        }
    return nbrs


def _ssh_poe_brief_throttled(instance_id: int, connection: dict, min_interval_s: int) -> Dict[str, Dict[str, Any]]:
    now = time.time()
    cache = _SSH_PORTS_CACHE.get(instance_id)
    if cache and (now - cache.get("ts_poe", 0) < max(60, min_interval_s)):
        return cache.get("poe", {})
    data = _ssh_poe_brief(connection)
    if cache is None:
        _SSH_PORTS_CACHE[instance_id] = {"ts_poe": now, "poe": data}
    else:
        cache["ts_poe"] = now
        cache["poe"] = data
    return data


def _ssh_poe_brief(connection: dict) -> Dict[str, Dict[str, Any]]:
    """Parse 'show power-over-ethernet brief' per-port power draw and class.

    Returns mapping: port_id -> { poe_power_w: float, poe_class: str, poe_status: str }
    """
    out = ""
    poe: Dict[str, Dict[str, Any]] = {}
    with SSH(**_ssh_ctx(connection)) as conn:
        out = conn.send_command("show power-over-ethernet brief", expect_string=None)
    in_table = False
    for line in out.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("PoE") and "Port" in line and "Status" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if line.strip().startswith("------"):
            continue
        # Expected columns: Port Enab Priority Detect Cfg Actual Rsrvd PD Pwr Draw Status PLC Cls Type
        cols = [c for c in line.split() if c]
        if len(cols) < 5:
            continue
        port_id = cols[0]
        # Find PD Pwr and Status by searching tokens
        # Look for a token like '<num> W'
        pd_power = None
        for i, tok in enumerate(cols):
            if tok.endswith('W') and tok[:-1].replace('.', '', 1).isdigit():
                try:
                    pd_power = float(tok[:-1])
                except Exception:
                    pd_power = None
        status = cols[-3] if len(cols) >= 3 else None  # 'Delivering' etc.
        poe_class = cols[-2] if len(cols) >= 2 else None
        poe[port_id] = {
            "poe_power_w": pd_power,
            "poe_class": poe_class,
            "poe_status": status,
        }
    return poe


def _infer_media_from_type(type_str: str) -> str:
    t = (type_str or '').lower()
    if any(k in t for k in ("sfp", "sr", "lr", "lc", "sc", "xfp", "qsfp")):
        return "fiber"
    if any(k in t for k in ("gbe-t", "1000t", "100/1000t", "rj45", "base-t", "t")):
        return "copper"
    return "unknown"


class ArubaOSSwitchDriver:
    """
    Aruba OS-S Switch Driver for walNUT Integration Framework.
    
    This driver provides comprehensive management for ArubaOS-S switches including:
    - Switch inventory and health monitoring
    - PoE port control and status
    - Network interface management 
    - Configuration backup and system reboot
    
    The driver uses both SSH and SNMP transports for switch communication.
    """
    
    def __init__(self, instance, secrets: Dict[str, str], transports):
        self.instance = instance
        self.config = instance.config
        self.secrets = secrets
        self.transports = transports
        
        # Per-instance logger
        type_id = getattr(instance, "type_id", "com.aruba.aoss")
        name = getattr(instance, "name", "unknown")
        self.logger = log  # Use the existing logger from the module
        
        # Validate required configuration (config fields)
        required_config_fields = ['hostname', 'username']
        for field in required_config_fields:
            if not self.config.get(field):
                raise ValueError(f"Required configuration field '{field}' is missing")
        
        # Validate required secrets
        required_secret_fields = ['password', 'snmp_community']
        for field in required_secret_fields:
            if not self.secrets.get(field):
                raise ValueError(f"Required secret field '{field}' is missing")
        
        self.logger.info(
            "Initialized ArubaOS-S driver for %s (%s)", 
            self.config.get("hostname"), 
            name
        )
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connectivity to the Aruba switch using both SSH and SNMP.
        """
        connection = self._build_connection_dict()
        
        try:
            # Test basic connectivity and get switch info
            start_time = time.time()
            
            # Try SNMP first (faster)
            try:
                latency_ms = _latency_probe(connection)
                self.logger.info("SNMP connectivity test successful, latency: %dms", latency_ms)
            except Exception as e:
                self.logger.warning("SNMP test failed: %s", e)
                return {
                    "status": "error", 
                    "message": f"SNMP connection failed: {str(e)}"
                }
            
            # Test SSH connectivity
            try:
                with SSH(
                    host=connection["hostname"],
                    username=connection["username"],
                    password=connection["password"],
                    device_type=connection.get("device_type", "aruba_osswitch"),
                    timeout=connection.get("timeout_s", 30)
                ) as ssh:
                    # Simple command to verify SSH works
                    output = ssh.send_command("show version | include Software")
                    if "Software" in output:
                        self.logger.info("SSH connectivity test successful")
                    else:
                        self.logger.warning("SSH command returned unexpected output")
            except Exception as e:
                self.logger.warning("SSH test failed: %s", e)
                return {
                    "status": "error",
                    "message": f"SSH connection failed: {str(e)}"
                }
            
            total_time = time.time() - start_time
            return {
                "status": "connected",
                "latency_ms": int(latency_ms),
                "total_test_time": round(total_time, 2),
                "transports_tested": ["snmp", "ssh"]
            }
            
        except Exception as e:
            self.logger.error("Connection test failed: %s", e)
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def heartbeat(self) -> Dict[str, Any]:
        """
        Lightweight health check for the switch.
        """
        connection = self._build_connection_dict()
        
        try:
            # Quick SNMP probe
            start_time = time.time()
            latency_ms = _latency_probe(connection)
            
            return {
                "state": "connected",
                "latency_ms": latency_ms,
                "checked_at": time.time()
            }
        except Exception as e:
            self.logger.error("Heartbeat failed: %s", e)
            return {
                "state": "error",
                "error_code": "connection_failed",
                "latency_ms": None
            }
    
    async def inventory_list(self, target_type: str, active_only: bool = True, options: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """List inventory targets according to walNUT inventory contract.
        
        Args:
            target_type: "vm"|"stack-member"|"port" - target type to list
            active_only: If True, only return active targets
            options: Additional options (currently unused)
            
        Returns:
            List of targets in standardized format:
            Stack: {type:"stack-member", id:"<member_id>", name:"Member <id>", attrs:{model:<str>}, labels:{}}
            Port: {type:"port", id:"<port-id>", name:"<alias|description|id>", attrs:{poe:<bool>, link:"up|down", speed?:<str>}, labels:{}}
        """
        # Accept both underscore and hyphen style target types; normalize to underscore for outputs
        if target_type in ("stack_member", "stack-member"):
            return await self._list_stack_members()
        elif target_type in ("port", "poe-port", "poe_port", "interface"):
            poll_mode = (self.config.get("poll_mode") or "snmp").lower()
            force_ssh = poll_mode == "ssh"
            return await self._list_ports(active_only, force_ssh=force_ssh)
        # Return empty list for unsupported types (vm, etc.) instead of raising error
        return []
    
    async def switch_inventory(self, target, dry_run: bool = False) -> Dict[str, Any]:
        """
        Get switch inventory information.
        """
        connection = self._build_connection_dict()
        return execute("switch.inventory", "read", target, {}, connection, dry_run)
    
    async def switch_health(self, target, dry_run: bool = False) -> Dict[str, Any]:
        """
        Get switch health status.
        """
        connection = self._build_connection_dict()
        return execute("switch.health", "read", target, {}, connection, dry_run)
    
    async def poe_status(self, target, dry_run: bool = False) -> Dict[str, Any]:
        """
        Get PoE status information.
        """
        connection = self._build_connection_dict()
        return execute("poe.status", "read", target, {}, connection, dry_run)
    
    async def poe_port(self, target, params: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """
        Set PoE port state (on/off/cycle).
        """
        connection = self._build_connection_dict()
        return execute("poe.port", "set", target, params, connection, dry_run)
    
    async def poe_priority(self, target, params: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """
        Set PoE port priority (low/high/critical).
        """
        connection = self._build_connection_dict()
        return execute("poe.priority", "set", target, params, connection, dry_run)
    
    async def net_interface(self, target, params: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """
        Set network interface admin state (up/down).
        """
        connection = self._build_connection_dict()
        return execute("net.interface", "set", target, params, connection, dry_run)
    
    async def switch_config(self, target, params: Dict[str, Any] = None, dry_run: bool = False) -> Dict[str, Any]:
        """
        Save or backup switch configuration.
        """
        connection = self._build_connection_dict()
        action = params.get("action", "save") if params else "save"
        return execute("switch.config", action, target, params or {}, connection, dry_run)
    
    async def config_backup(self, target, dry_run: bool = False) -> Dict[str, Any]:
        """
        Backup switch configuration.
        """
        connection = self._build_connection_dict()
        return execute("switch.config", "backup", target, {}, connection, dry_run)
    
    async def switch_reboot(self, target, params: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """
        Reboot the switch.
        """
        connection = self._build_connection_dict()
        return execute("switch.reboot", "exec", target, params, connection, dry_run)
    
    async def _list_stack_members(self) -> List[Dict[str, Any]]:
        """List stack members according to walNUT inventory contract.
        
        Returns stack member targets in format:
        {type:"stack-member", id:"<member_id>", name:"Member <id>", attrs:{model:<str>}, labels:{}}
        """
        connection = self._build_connection_dict()
        
        try:
            # Check if switch is stacked by trying to get stack status
            # For non-stacked switches, this should return empty list
            result = _get_stack_info(connection)
            
            targets = []
            for member in result.get("members", []):
                member_id = str(member.get("id", ""))
                if not member_id:
                    continue
                    
                targets.append({
                    "type": "stack_member",
                    "id": member_id,
                    "external_id": member_id,  # Keep for compatibility
                    "name": f"Member {member_id}",
                    "attrs": {
                        "model": member.get("model", "Unknown"),
                        "status": member.get("status", "unknown"),
                        "priority": member.get("priority"),
                        "role": member.get("role"),  # master/member
                    },
                    "labels": {},
                })
            
            return targets
            
        except Exception as e:
            self.logger.debug("Stack info not available (likely single switch): %s", e)
            # Return empty list for non-stacked switches
            return []
    
    async def _list_ports(self, active_only: bool = True, force_ssh: bool = False) -> List[Dict[str, Any]]:
        """List switch ports (real SNMP-backed).
        
        Active ports definition: link == 'up' OR PoE delivering power.
        """
        connection = self._build_connection_dict()
        try:
            if force_ssh:
                ports_list = _ssh_ports_fallback_throttled(getattr(self.instance, 'instance_id', 0), connection, int(self.config.get("ssh_min_poll_seconds", 180)))
                info = {"ports": ports_list}
            else:
                info = _get_port_info(connection)
            targets: List[Dict[str, Any]] = []
            raw_ports = info.get("ports", [])
            # Optional LLDP + PoE enrichment via SSH (throttled)
            neighbors = {}
            poe_map = {}
            try:
                neighbors = _ssh_lldp_neighbors_throttled(getattr(self.instance, 'instance_id', 0), connection, int(self.config.get("ssh_min_poll_seconds", 180)))
            except Exception:
                neighbors = {}
            try:
                poe_map = _ssh_poe_brief_throttled(getattr(self.instance, 'instance_id', 0), connection, int(self.config.get("ssh_min_poll_seconds", 180)))
            except Exception:
                poe_map = {}
            for port in raw_ports:
                port_id = str(port.get("port_id", ""))
                if not port_id:
                    continue

                name = (
                    port.get("alias")
                    or port.get("description")
                    or port.get("if_name")
                    or port_id
                )

                link_status = "up" if str(port.get("if_oper", "2")).strip() in ("1", "up") else "down"
                poe_present = bool(port.get("poe_power")) or bool(port.get("poe_supported"))
                if active_only and not (link_status == "up" or poe_present):
                    continue

                # Prefer SNMP media; if missing and SSH hinted, use SSH type hint
                media = _infer_media_type(str(port.get("if_type", "")), str(port.get("description", "")))
                if (not media or media == 'unknown') and port.get('_media_hint'):
                    media = port['_media_hint']

                speed_mbps = None
                if port.get("if_high_speed"):
                    try:
                        speed_mbps = int(port.get("if_high_speed"))
                    except Exception:
                        speed_mbps = None
                elif port.get("speed"):
                    try:
                        speed_mbps = int(int(port.get("speed")) / 1_000_000)
                    except Exception:
                        speed_mbps = None

                attrs: Dict[str, Any] = {"link": link_status, "media": media}
                if speed_mbps is not None:
                    attrs["speed_mbps"] = speed_mbps
                if port.get("poe_class"):
                    attrs["poe_class"] = port["poe_class"]
                if port.get("poe_power") is not None:
                    attrs["poe_power_w"] = port["poe_power"]

                # Attach LLDP neighbor if present
                nbr = neighbors.get(port_id)
                if nbr:
                    attrs["lldp"] = nbr
                # Attach PoE info from SSH brief if present
                p = poe_map.get(port_id)
                if p:
                    if p.get('poe_power_w') is not None:
                        attrs['poe_power_w'] = p['poe_power_w']
                    if p.get('poe_class') is not None:
                        attrs['poe_class'] = p['poe_class']

                targets.append(
                    {
                        "type": "port",
                        "id": port_id,
                        "external_id": port_id,
                        "name": name,
                        "attrs": attrs,
                        "labels": {},
                    }
                )
            try:
                self.logger.info("AOSS inventory_list ports returned=%d (active_only=%s)", len(targets), str(active_only))
            except Exception:
                pass
            return targets
        except Exception as e:
            self.logger.error("Failed to get port information: %s", e)
            return []
    
    def _build_connection_dict(self) -> Dict[str, Any]:
        """
        Build connection dictionary from configuration and secrets.
        """
        return {
            "hostname": self.config["hostname"],
            "username": self.config["username"],
            "password": self.secrets["password"],  # Password comes from secrets
            "enable_password": self.secrets.get("enable_password"),  # Enable password also from secrets
            "ssh_port": self.config.get("ssh_port", 22),
            "timeout_s": self.config.get("timeout_s", 30),
            "device_type": self.config.get("device_type", "aruba_osswitch"),
            "snmp_community": self.secrets.get("snmp_community", "public"),  # SNMP community from secrets
            "snmp_host": self.config.get("snmp_host"),
            "snmp_port": self.config.get("snmp_port", 161)
        }


def _infer_media_type(if_type: str, descr: str) -> str:
    """Heuristic media type from ifType numeric or description string.
    Returns: 'fiber' | 'copper' | 'unknown'
    """
    d = (descr or '').lower()
    if any(tok in d for tok in ("sfp", "fiber", "gbic", "xfp", "qsfp", " lc", " sc")):
        return "fiber"
    if any(tok in d for tok in ("rj45", "copper", "base-t", "base t", "utp")):
        return "copper"
    # Fallback on ifType numeric hints if present
    try:
        _ = int(if_type)
    except Exception:
        pass
    return "unknown"
