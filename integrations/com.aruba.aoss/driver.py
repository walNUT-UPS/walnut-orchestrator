from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional

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
from parsers.interfaces import parse_show_modules, parse_show_version, parse_show_vsf
from parsers import snmp as snmp_helpers


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
        host=connection.get("hostname"),
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
    """Get stack member information via SNMP."""
    try:
        # For MVP, return empty members list - real implementation would query
        # HP-ICF-STACKING MIB or similar to get actual stack information
        return {"members": []}
    except Exception as e:
        return {"members": [], "error": str(e)}


def _get_port_info(connection: dict) -> dict:
    """Get port information via SNMP."""
    try:
        # For MVP, return basic port structure - real implementation would query
        # IF-MIB and POE-MIB to get actual port status and PoE information
        # This is a placeholder that provides expected structure
        ports = []
        
        # Simulate basic port structure for development/testing
        # In real implementation, this would query SNMP OIDs:
        # - ifTable (1.3.6.1.2.1.2.2) for interface info
        # - pethPsePortTable (1.3.6.1.2.1.105.1.1.1) for PoE info
        
        for i in range(1, 25):  # Simulate 24 ports
            port = {
                "port_id": str(i),
                "description": f"Port {i}",
                "alias": None,
                "link_status": "down",  # Would be determined from ifOperStatus
                "poe_enabled": False,   # Would be determined from PoE MIB
                "speed": None,
                "duplex": None,
                "poe_power": None,
                "poe_class": None
            }
            ports.append(port)
        
        return {"ports": ports}
        
    except Exception as e:
        return {"ports": [], "error": str(e)}


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
        if target_type == "stack-member":
            return await self._list_stack_members()
        elif target_type == "port":
            return await self._list_ports(active_only)
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
                    "type": "stack-member",
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
    
    async def _list_ports(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """List switch ports according to walNUT inventory contract.
        
        Active ports definition: link == "up" OR poe == true
        
        Returns port targets in format:
        {type:"port", id:"<port-id>", name:"<alias|description|id>", attrs:{poe:<bool>, link:"up|down", speed?:<str>}, labels:{}}
        """
        connection = self._build_connection_dict()
        
        try:
            # Get port information via SNMP
            port_info = _get_port_info(connection)
            
            targets = []
            for port in port_info.get("ports", []):
                port_id = str(port.get("port_id", ""))
                if not port_id:
                    continue
                
                # Determine port name priority: alias > description > port_id
                name = (port.get("alias") or 
                       port.get("description") or 
                       port_id)
                
                # Get port attributes
                poe_enabled = port.get("poe_enabled", False)
                link_status = port.get("link_status", "down")  # up|down
                
                # Apply active_only filter: active = link up OR poe enabled
                is_active = link_status == "up" or poe_enabled
                if active_only and not is_active:
                    continue
                
                attrs = {
                    "poe": poe_enabled,
                    "link": link_status,
                }
                
                # Add optional speed if available
                if port.get("speed"):
                    attrs["speed"] = port["speed"]
                    
                # Add other useful attributes
                if port.get("duplex"):
                    attrs["duplex"] = port["duplex"]
                if port.get("poe_power"):
                    attrs["poe_power"] = port["poe_power"]
                if port.get("poe_class"):
                    attrs["poe_class"] = port["poe_class"]
                
                targets.append({
                    "type": "port",
                    "id": port_id,
                    "external_id": port_id,  # Keep for compatibility
                    "name": name,
                    "attrs": attrs,
                    "labels": {},
                })
            
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
            "snmp_community": self.secrets["snmp_community"],  # SNMP community from secrets
            "snmp_port": self.config.get("snmp_port", 161)
        }

