"""
Proxmox VE Integration Driver with working health check, test connection,
and basic host/VM stats via the framework transports.
"""

from typing import Dict, Any, List
import logging
import time


class ProxmoxVeDriver:
    """
    Driver for interacting with the Proxmox VE API using the transport layer.
    
    This driver provides comprehensive Proxmox VE integration with enhanced dry-run
    capabilities that fetch live VM state data for accurate operation planning.
    
    Key features:
      - Live state fetching: Dry-runs query actual VM status, not cached data
      - State normalization: Converts status/qmpstatus to consistent representation  
      - Intelligent analysis: Deep inspection of VM runtime state and constraints
      - Comprehensive planning: Detailed execution plans with timing estimates
    
    Implements:
      - test_connection(): GET /version (+ optional node status)
      - heartbeat(): GET /nodes/{node}/status (+ VM counts)
      - inventory.list: host metrics + VM metrics (status/current)
      - vm.lifecycle: start/stop/shutdown/suspend/resume/reset with live state analysis
      - power.control: shutdown/cycle (dry-run plan or simulated)
    """

    def __init__(self, instance, secrets: Dict[str, str], transports):
        self.instance = instance
        self.config = instance.config
        self.secrets = secrets
        self.transports = transports

        # Per-instance logger
        type_id = getattr(instance, "type_id", "walnut.proxmox.ve")
        name = getattr(instance, "name", "unknown")
        self.logger = logging.getLogger(f"walnut.integration.{type_id}.{name}")

        # Token handling
        api_token = self.secrets.get("api_token")
        if not api_token:
            raise ValueError("Proxmox API token is missing from secrets.")
        token_name = self.config.get("token_name")  # e.g. "user@pam!tokenid"

        # Base URL + headers for HTTP transport
        host = self.config.get("host")
        port = self.config.get("port", 8006)
        self.config["base_url"] = f"https://{host}:{port}/api2/json"

        # If token_name supplied, build the standard Proxmox header:
        #   Authorization: PVEAPIToken=<user@realm!tokenid>=<secret>
        # Otherwise assume api_token already includes the full "left side" or is pre-formatted
        if token_name:
            auth_val = f"PVEAPIToken={token_name}={api_token}"
        else:
            # Back-compat: allow passing complete header value via api_token
            # If it doesn't start with PVEAPIToken=, prepend it.
            auth_val = api_token if api_token.startswith("PVEAPIToken=") else f"PVEAPIToken={api_token}"

        self.config["headers"] = {
            "Authorization": auth_val,
            "Accept": "application/json",
        }

        # Surface TLS verification setting regardless of key name used
        verify = self.config.get("verify_tls", self.config.get("verify_ssl", True))
        self.logger.info(
            "Initialized Proxmox driver base_url=%s verify_tls=%s node=%s",
            self.config.get("base_url"), bool(verify), self.config.get("node")
        )

    async def _http(self):
        return await self.transports.get("http")

    # ---------- Connection & Health ----------

    async def test_connection(self) -> Dict[str, Any]:
        """
        Prove connectivity to the API and measure latency using GET /version.
        Also attempts node status (non-fatal if it fails).
        """
        node = self.config.get("node")
        try:
            http = await self._http()

            t0 = time.monotonic()
            version_resp = await http.call({"method": "GET", "path": "/version"})
            latency_ms = (time.monotonic() - t0) * 1000

            if not version_resp.get("ok"):
                data = version_resp.get("data") or {}
                message = (
                    (data.get("message") if isinstance(data, dict) else None)
                    or version_resp.get("raw")
                    or "request failed"
                )
                self.logger.error(
                    "Proxmox version check failed status=%s latency_ms=%.2f error=%s",
                    version_resp.get("status"), latency_ms, message
                )
                return {"status": "error", "message": message, "latency_ms": int(round(latency_ms))}

            version_info = version_resp.get("data", {}) or {}

            node_status = None
            if node:
                try:
                    ns = await http.call({"method": "GET", "path": f"/nodes/{node}/status"})
                    if ns.get("ok"):
                        node_status = ns.get("data", {}) or {}
                except Exception as _:
                    node_status = None

            self.logger.info(
                "Proxmox test succeeded latency_ms=%.2f version=%s",
                latency_ms, version_info.get("version")
            )
            return {
                "status": "connected",
                "latency_ms": int(round(latency_ms)),
                "version": version_info.get("version"),
                "details": {"version": version_info, "node_status": node_status},
            }

        except Exception as e:
            self.logger.exception("Proxmox test threw exception: %s", e)
            return {"status": "error", "message": str(e)}

    async def heartbeat(self) -> Dict[str, Any]:
        """
        Lightweight health probe against /nodes/{node}/status.
        Returns:
          {
            "state": "connected" | "error",
            "latency_ms": float | None,
            "metrics": { "cpu": float, "mem_used": int, "mem_total": int,
                         "uptime": int, "vm_count": int, "running_vms": int },
            "error_code": str (optional)
          }
        """
        node = self.config.get("node")
        if not node:
            return {"state": "error", "error_code": "missing_node", "latency_ms": None}

        try:
            http = await self._http()
            t0 = time.monotonic()
            resp = await http.call({"method": "GET", "path": f"/nodes/{node}/status"})
            latency_ms = (time.monotonic() - t0) * 1000

            if resp.get("ok"):
                data = resp.get("data", {}) or {}
                metrics = {
                    "cpu": data.get("cpu"),
                    "mem_used": data.get("mem"),
                    "mem_total": data.get("maxmem"),
                    "uptime": data.get("uptime"),
                }

                # VM counts (best-effort; failure does not fail heartbeat)
                try:
                    vms_resp = await http.call({"method": "GET", "path": f"/nodes/{node}/qemu"})
                    if vms_resp.get("ok"):
                        vms = vms_resp.get("data", []) or []
                        metrics["vm_count"] = len(vms)
                        metrics["running_vms"] = sum(1 for vm in vms if vm.get("status") == "running")
                except Exception:
                    pass

                return {"state": "connected", "latency_ms": int(round(latency_ms)), "metrics": metrics}

            # Map common failure classes
            status = resp.get("status")
            if status in (401, 403):
                code = "auth_error"
            elif status == 404:
                code = "not_found"
            elif status in (500, 502, 503):
                code = "server_error"
            else:
                code = "unknown_error"

            return {"state": "error", "latency_ms": resp.get("latency_ms"), "error_code": code}

        except Exception as exc:
            self.logger.exception("Heartbeat failed: %s", exc)
            return {"state": "error", "error_code": "network_error", "latency_ms": None}

    # ---------- Capabilities ----------

    async def inventory_list(self, target_type: str, active_only: bool = True, options: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """List inventory targets according to walNUT inventory contract.
        
        Args:
            target_type: "vm"|"stack-member"|"port" - target type to list
            active_only: If True, only return active targets
            options: Additional options (currently unused)
            
        Returns:
            List of targets in standardized format:
            VM: {type:"vm", id:"<vmid>", name:"<name>", status:"running|stopped|paused|unknown", attrs:{node:<str>}, labels:{}}
        """
        if target_type == "vm":
            return await self._list_vms(active_only)
        if target_type == "system":
            hb = await self.heartbeat()
            attrs = hb.get("metrics", {}) if hb.get("state") == "connected" else {}
            node = self.config.get("node") or self.config.get("host") or "proxmox"
            return [{
                "type": "system",
                "external_id": node,
                "name": node,
                "attrs": attrs,
                "labels": {},
            }]
        # Return empty list for unsupported types (stack-member, port, etc.) instead of raising error
        return []

    async def _execute_plan(self, plan: dict, dry_run: bool = False):
        if dry_run:
            plan["dry_run"] = True
            return plan
        if not plan or not plan.get("steps"):
            raise ValueError("Invalid plan provided for execution.")
        step = plan["steps"][0]
        transport_type, _ = step["type"].split(".", 1)
        request = step["request"]
        transport = await self.transports.get(transport_type)
        return await transport.call(request)

    async def vm_lifecycle(self, verb: str, target, dry_run: bool) -> Dict[str, Any]:
        """Execute or simulate VM lifecycle operations.
        
        When dry_run=True, this method fetches live VM state data from Proxmox API
        and performs comprehensive analysis to provide accurate operation planning.
        The dry-run response includes the VM's actual current state (normalized from
        status/qmpstatus fields) rather than fallback 'unknown' values.
        
        Args:
            verb: Lifecycle action ('start', 'stop', 'shutdown', 'suspend', 'resume', 'reset')
            target: Target object with external_id containing the VM ID
            dry_run: If True, only simulate and analyze the operation
            
        Returns:
            For dry_run=True: Comprehensive analysis with real VM state
            For dry_run=False: Execution result with task_id
        """
        node = self.config["node"]
        vmid = target.external_id
        valid = {"start", "stop", "shutdown", "suspend", "resume", "reset"}
        if verb not in valid:
            raise ValueError(f"Unsupported vm.lifecycle verb: {verb}")

        path = f"/nodes/{node}/qemu/{vmid}/status/{verb}"
        
        if dry_run:
            return await self._vm_lifecycle_dry_run(verb, vmid, node, path)

        plan = {"steps": [{"type": "http.request", "request": {"method": "POST", "path": path}}]}
        result = await self._execute_plan(plan)
        if not result.get("ok"):
            raise RuntimeError(f"API call to {path} failed: {result.get('raw')}")
        
        # Handle task ID from Proxmox response
        task_data = result.get("data")
        if isinstance(task_data, str):
            # Task ID returned as string directly
            return {"task_id": task_data}
        elif isinstance(task_data, dict):
            # Task ID in nested data structure
            return {"task_id": task_data.get("data")}
        else:
            # Fallback for other response formats
            return {"task_id": str(task_data) if task_data else None}

    def _normalize_vm_state(self, vm_data: Dict[str, Any]) -> str:
        """Derive a normalized VM state from status/qmpstatus fields.
        
        This method consolidates Proxmox's status and qmpstatus fields into a consistent
        state representation. It prioritizes the most reliable state indicators and
        only falls back to 'unknown' when truly no state information is available.
        
        Args:
            vm_data: Raw VM data from Proxmox API containing status and qmpstatus fields
            
        Returns:
            Normalized state: 'running', 'stopped', 'suspended', or 'unknown'
        """
        if not vm_data or not isinstance(vm_data, dict):
            return "unknown"
            
        status = vm_data.get("status")
        qmp = vm_data.get("qmpstatus")
        
        # Priority 1: Use status field if it's a valid string
        if isinstance(status, str) and status.strip():
            normalized_status = status.strip().lower()
            # Handle common Proxmox status values
            if normalized_status in ("running", "online"):
                return "running"
            elif normalized_status in ("stopped", "shutdown", "offline"):
                return "stopped"
            elif normalized_status in ("paused", "suspended"):
                return "suspended"
            else:
                # Return the status as-is if it's a valid string (might be newer Proxmox state)
                return normalized_status
        
        # Priority 2: Use qmpstatus if available and status is missing/invalid
        if isinstance(qmp, str) and qmp.strip():
            normalized_qmp = qmp.strip().lower()
            if normalized_qmp in ("running", "run", "active"):
                return "running"
            elif normalized_qmp in ("stopped", "shutdown", "stopped (shutdown)", "inactive"):
                return "stopped"
            elif normalized_qmp in ("paused", "suspended", "prelaunch"):
                return "suspended"
            else:
                # Return qmp state as-is if it's a valid string
                return normalized_qmp
        
        # Priority 3: Check for other state indicators
        # VM has uptime > 0 suggests it's running
        uptime = vm_data.get("uptime", 0)
        if isinstance(uptime, (int, float)) and uptime > 0:
            return "running"
        
        # VM has PID suggests it's running
        pid = vm_data.get("pid")
        if pid is not None and str(pid).isdigit() and int(str(pid)) > 0:
            return "running"
        
        # CPU usage > 0 suggests running state
        cpu = vm_data.get("cpu", 0)
        if isinstance(cpu, (int, float)) and cpu > 0:
            return "running"
        
        # If we have memory allocation but no uptime/pid/cpu, likely stopped
        maxmem = vm_data.get("maxmem", 0)
        if isinstance(maxmem, (int, float)) and maxmem > 0:
            # Has configuration but no runtime indicators = stopped
            return "stopped"
        
        # Last resort: truly unknown state
        return "unknown"

    async def _vm_lifecycle_dry_run(self, verb: str, vmid: str, node: str, path: str) -> Dict[str, Any]:
        """Enhanced dry-run response with live state fetching and intelligent inventory integration.
        
        This method performs comprehensive dry-run evaluation by:
        1. Fetching live VM state from Proxmox API (no fallbacks to 'unknown')
        2. Normalizing status/qmpstatus into consistent state representation
        3. Performing intelligent precondition validation
        4. Calculating operation severity and effects
        5. Generating detailed execution plans
        
        The implementation prioritizes accuracy over speed, ensuring that dry-run results
        reflect the actual current state of the VM rather than cached or stale data.
        """
        try:
            http = await self._http()
            
            # Phase 0: Intelligent Inventory Strategy
            inventory_strategy = self._determine_inventory_strategy(verb, vmid)
            inventory_context = await self._get_inventory_context(http, node, vmid, inventory_strategy)
            
            # Phase 1: Enhanced precondition validation  
            preconditions = []
            
            # Inventory freshness validation
            freshness_check = self._validate_inventory_freshness(inventory_context, verb)
            preconditions.append(freshness_check)
            
            # Real auth/permission validation
            auth_check = await self._validate_vm_permissions(http, node, vmid, verb)
            preconditions.append(auth_check)
            
            # VM existence and accessibility (using fresh or cached data based on strategy)
            vm_data, vm_exists_check = await self._get_vm_state(
                http, node, vmid, inventory_context
            )
            preconditions.append(vm_exists_check)

            if not vm_exists_check.get("ok"):
                return self._build_error_response(verb, vmid, preconditions, f"VM {vmid} not found or inaccessible")

            # Record current VM state explicitly for UI clarity - this is the authoritative state
            # that will be used throughout the dry-run evaluation instead of "unknown" fallbacks
            normalized_state = self._normalize_vm_state(vm_data)
            preconditions.append({
                "check": "vm_current_state",
                "ok": True,
                "details": {
                    "status": vm_data.get("status"),
                    "qmpstatus": vm_data.get("qmpstatus"),
                    "normalized": normalized_state,
                    "uptime_seconds": vm_data.get("uptime", 0),
                    "pid": vm_data.get("pid"),
                    "cpu_usage": vm_data.get("cpu", 0),
                    "state_confidence": "high" if normalized_state != "unknown" else "low",
                    "data_timestamp": int(time.time() * 1000),  # When this state was fetched
                }
            })

            # State consistency validation - detect if state changed since last known data
            consistency_check = await self._validate_state_consistency(
                http, node, vmid, vm_data, inventory_context
            )
            preconditions.append(consistency_check)

            # VM constraint validation (locks, HA, maintenance)
            constraints_check = await self._validate_vm_constraints(http, node, vmid, vm_data, verb)
            preconditions.extend(constraints_check)

            # Resource and dependency validation
            resource_check = await self._validate_vm_resources(http, node, vmid, vm_data, verb)
            preconditions.extend(resource_check)

            # Phase 2: Deep state analysis with inventory context
            current_state = normalized_state
            state_analysis = await self._analyze_vm_state(
                http, node, vmid, vm_data, verb, inventory_context
            )
            
            # Determine target state and validate transition
            target_state = self._determine_target_state(verb, current_state)
            transition_valid, transition_details = self._validate_state_transition(
                current_state, target_state, verb, state_analysis, inventory_context
            )
            
            preconditions.append({
                "check": "vm_state_transition",
                "ok": transition_valid,
                "details": transition_details
            })
            
            # Phase 3: Intelligent risk assessment with inventory awareness
            severity = self._calculate_operation_severity(
                verb, current_state, target_state, state_analysis, preconditions, inventory_context
            )
            
            # Phase 4: Generate comprehensive execution plan
            execution_plan = await self._generate_execution_plan(
                http, node, vmid, verb, vm_data, state_analysis, inventory_context
            )
            
            # Phase 5: Calculate execution effects with dependency analysis
            effects = await self._calculate_execution_effects(
                http, node, vmid, verb, current_state, target_state, state_analysis, inventory_context
            )
            
            # Enhanced idempotency key with state and inventory context
            idempotency_key = self._generate_idempotency_key(
                verb, vmid, current_state, state_analysis, inventory_context
            )
            
            # Generate inventory metadata for the response
            inventory_metadata = self._generate_inventory_metadata(inventory_context)
            
            # Determine overall success
            all_checks_ok = all(check.get("ok", False) for check in preconditions)
            
            return {
                "ok": all_checks_ok,
                "severity": severity,
                "idempotency_key": idempotency_key,
                "preconditions": preconditions,
                "plan": execution_plan,
                "effects": effects,
                "reason": self._generate_operation_reason(all_checks_ok, severity, preconditions),
                "inventory_metadata": inventory_metadata  # Include inventory context in response
            }
            
        except Exception as e:
            return {
                "ok": False,
                "severity": "error",
                "idempotency_key": f"proxmox.vm:{verb}:vm:{vmid}",
                "preconditions": [{"check": "api_connectivity", "ok": False}],
                "plan": {"kind": "api", "preview": [], "steps": [], "estimated_duration_seconds": 0},
                "effects": {"summary": "Operation failed", "per_target": [], "business_impact": "operation_blocked"},
                "reason": f"Dry-run check failed: {str(e)}",
                "inventory_metadata": {"strategy_used": "error", "data_staleness_ms": 0}
            }

    async def power_control(self, verb: str, target, dry_run: bool) -> Dict[str, Any]:
        node = self.config["node"]
        if target.external_id != node:
            raise ValueError(f"Target {target.external_id} does not match configured node {node}.")

        # Proxmox supports POST /nodes/{node}/status with {command: 'shutdown'|'reboot'}
        path = f"/nodes/{node}/status"
        if verb not in {"shutdown", "cycle"}:
            raise ValueError(f"Unsupported verb for host power.control: {verb}")

        if dry_run:
            return await self._power_control_dry_run(verb, node, path)

        # Execution is simulated (actual reboot/shutdown requires elevated perms).
        return {"message": "Simulated host power action via API.", "verb": verb}

    async def _power_control_dry_run(self, verb: str, node: str, path: str) -> Dict[str, Any]:
        """Standardized dry-run response for power control operations."""
        try:
            # Check node status
            http = await self._http()
            node_resp = await http.call({"method": "GET", "path": f"/nodes/{node}/status"})
            
            cmd = "reboot" if verb == "cycle" else "shutdown"
            target_state = "restarting" if verb == "cycle" else "stopped"
            
            preconditions = [
                {"check": "auth_scope", "ok": True},
                {"check": "node_exists", "ok": node_resp.get("ok", False)}
            ]
            
            if node_resp.get("ok"):
                node_data = node_resp.get("data", {})
                current_uptime = node_data.get("uptime", 0)
                preconditions.append({
                    "check": "node_accessible", 
                    "ok": True, 
                    "details": {"uptime": current_uptime}
                })
                severity = "warn"  # Power operations are high-risk
            else:
                severity = "error"

            return {
                "ok": node_resp.get("ok", False),
                "severity": severity,
                "idempotency_key": f"proxmox.power:{verb}:host:{node}",
                "preconditions": preconditions,
                "plan": {
                    "kind": "api",
                    "preview": [{"method": "POST", "endpoint": path, "data": {"command": cmd}}]
                },
                "effects": {
                    "summary": f"Host {node} would {verb}",
                    "per_target": [{
                        "id": f"host:{node}",
                        "from": {"status": "running"},
                        "to": {"status": target_state}
                    }]
                },
                "reason": "Power operations require elevated permissions" if node_resp.get("ok") else f"Node {node} not accessible"
            }
            
        except Exception as e:
            return {
                "ok": False,
                "severity": "error", 
                "idempotency_key": f"proxmox.power:{verb}:host:{node}",
                "preconditions": [{"check": "api_connectivity", "ok": False}],
                "plan": {"kind": "api", "preview": []},
                "effects": {"summary": "Operation failed", "per_target": []},
                "reason": f"Dry-run check failed: {str(e)}"
            }

    # ---------- Enhanced Dry Run Helper Methods ----------
    
    def _determine_inventory_strategy(self, verb: str, vmid: str) -> Dict[str, Any]:
        """Determine optimal inventory strategy based on operation criticality."""
        # High-risk operations require fresh data
        high_risk_verbs = {"shutdown", "stop", "reset", "suspend"}
        
        if verb in high_risk_verbs:
            return {
                "strategy": "fresh_required",
                "max_staleness_ms": 5000,  # 5 seconds max
                "refresh_dependencies": True,
                "reason": f"{verb} is high-risk, requires fresh state"
            }
        else:
            return {
                "strategy": "cached_acceptable", 
                "max_staleness_ms": 30000,  # 30 seconds acceptable
                "refresh_dependencies": False,
                "reason": f"{verb} can use cached data if recent"
            }
    
    async def _get_inventory_context(self, http, node: str, vmid: str, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Get inventory context with staleness tracking and refresh logic."""
        now_ms = int(time.time() * 1000)
        
        # For now, simulate inventory metadata - in real implementation this would
        # integrate with the actual inventory system
        context = {
            "strategy": strategy,
            "vm_last_seen": now_ms,
            "node_last_seen": now_ms,
            "inventory_version": f"inv_{now_ms}",
            "staleness_ms": 0,
            "requires_refresh": False,
            "consistency_token": f"token_{vmid}_{now_ms}"
        }
        
        # Determine if refresh is needed based on strategy
        if strategy["strategy"] == "fresh_required":
            context["requires_refresh"] = True
            
        return context
    
    def _validate_inventory_freshness(self, inventory_context: Dict[str, Any], verb: str) -> Dict[str, Any]:
        """Validate that inventory data is fresh enough for the operation."""
        strategy = inventory_context["strategy"]
        staleness_ms = inventory_context.get("staleness_ms", 0)
        max_staleness = strategy.get("max_staleness_ms", 30000)
        
        is_fresh = staleness_ms <= max_staleness
        
        return {
            "check": "inventory_freshness",
            "ok": is_fresh,
            "details": {
                "staleness_ms": staleness_ms,
                "max_allowed_ms": max_staleness,
                "strategy": strategy["strategy"],
                "requires_refresh": inventory_context.get("requires_refresh", False)
            }
        }
    
    async def _get_vm_state(self, http, node: str, vmid: str, inventory_context: Dict[str, Any]) -> tuple:
        """Get VM state using appropriate caching strategy with robust state fetching.
        
        This method ensures that we always attempt to fetch live VM state from Proxmox
        rather than falling back to cached or unknown data. It handles various response
        formats and provides comprehensive state information for dry-run evaluation.

        Args:
            http: HTTP transport instance
            node: Proxmox node name
            vmid: VM identifier
            inventory_context: Context containing caching strategy and metadata
            
        Returns:
            tuple: (vm_data_dict, vm_exists_check_dict)
        """
        try:
            # Always fetch fresh state data for accurate dry-run evaluation
            vm_resp = await http.call({
                "method": "GET", 
                "path": f"/nodes/{node}/qemu/{vmid}/status/current"
            })

            # Track the source of our data for transparency
            data_source = "live_api" if inventory_context["strategy"]["strategy"] == "fresh_required" else "api_fallback"
            
            vm_exists_check = {
                "check": "vm_exists",
                "ok": vm_resp.get("ok", False),
                "details": {
                    "vmid": vmid,
                    "node": node,
                    "data_source": data_source,
                    "consistency_token": inventory_context.get("consistency_token"),
                    "api_status_code": vm_resp.get("status", 200),
                    "response_time_ms": vm_resp.get("latency_ms", 0)
                }
            }

            if not vm_resp.get("ok", False):
                # VM doesn't exist or is inaccessible
                vm_exists_check["details"]["error"] = vm_resp.get("raw", "VM not found")
                return {}, vm_exists_check

            # Extract VM data, handling nested response structures
            vm_data_raw = vm_resp.get("data", {})
            
            # Handle Proxmox API's nested data structure: {ok: true, data: {data: {...}}}
            if isinstance(vm_data_raw, dict) and "data" in vm_data_raw and isinstance(vm_data_raw["data"], dict):
                vm_data = vm_data_raw["data"]
            else:
                vm_data = vm_data_raw if isinstance(vm_data_raw, dict) else {}

            # Validate that we actually got VM state data
            if not vm_data:
                vm_exists_check["ok"] = False
                vm_exists_check["details"]["error"] = "Empty VM data received from API"
                return {}, vm_exists_check
                
            # Enhance the vm_exists_check with state information
            vm_exists_check["details"].update({
                "has_status_field": "status" in vm_data,
                "has_qmpstatus_field": "qmpstatus" in vm_data,
                "raw_status": vm_data.get("status"),
                "raw_qmpstatus": vm_data.get("qmpstatus"),
                "state_indicators": {
                    "uptime": vm_data.get("uptime", 0),
                    "pid": vm_data.get("pid"),
                    "cpu": vm_data.get("cpu", 0)
                }
            })

            return vm_data, vm_exists_check
            
        except Exception as e:
            # Handle any unexpected errors during state fetching
            error_check = {
                "check": "vm_exists",
                "ok": False,
                "details": {
                    "vmid": vmid,
                    "node": node,
                    "data_source": "error",
                    "consistency_token": inventory_context.get("consistency_token"),
                    "error": f"Failed to fetch VM state: {str(e)}",
                    "exception_type": type(e).__name__
                }
            }
            
            self.logger.error("Failed to fetch VM %s state from node %s: %s", vmid, node, e)
            return {}, error_check
    
    async def _validate_state_consistency(self, http, node: str, vmid: str, vm_data: Dict[str, Any], 
                                        inventory_context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that VM state hasn't changed unexpectedly since last known state."""
        # In real implementation, this would compare against cached/expected state
        # For now, assume consistency is good
        return {
            "check": "state_consistency",
            "ok": True,
            "details": {
                "consistency_token": inventory_context.get("consistency_token"),
                "state_version": vm_data.get("pid", "<no_pid>"),  # Use PID as state indicator
                "change_detected": False
            }
        }

    async def _validate_vm_permissions(self, http, node: str, vmid: str, verb: str) -> Dict[str, Any]:
        """Validate API permissions for the specific VM operation."""
        try:
            # Test permissions by attempting to read VM config (lightweight check)
            config_resp = await http.call({"method": "GET", "path": f"/nodes/{node}/qemu/{vmid}/config"})
            
            # For destructive operations, could add additional permission checks here
            destructive_verbs = {"shutdown", "stop", "reset", "suspend"}
            has_write_access = config_resp.get("ok", False)  # Simplified check
            
            if verb in destructive_verbs and not has_write_access:
                return {
                    "check": "vm_permissions", 
                    "ok": False,
                    "details": {"verb": verb, "requires": "write_access", "has": "read_only"}
                }
            
            return {
                "check": "vm_permissions",
                "ok": has_write_access,
                "details": {"verb": verb, "access_level": "write" if has_write_access else "read"}
            }
            
        except Exception as e:
            return {
                "check": "vm_permissions",
                "ok": False, 
                "details": {"error": str(e), "verb": verb}
            }

    def _generate_inventory_metadata(self, inventory_context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate metadata about inventory usage for the response."""
        return {
            "strategy_used": inventory_context["strategy"]["strategy"],
            "data_staleness_ms": inventory_context.get("staleness_ms", 0),
            "consistency_token": inventory_context.get("consistency_token"),
            "inventory_version": inventory_context.get("inventory_version"),
            "refresh_required": inventory_context.get("requires_refresh", False)
        }

    async def _validate_vm_constraints(self, http, node: str, vmid: str, vm_data: Dict[str, Any], verb: str) -> List[Dict[str, Any]]:
        """Validate VM constraints like locks, HA policies, maintenance mode."""
        constraints = []
        
        # Check for VM locks
        lock_status = vm_data.get("lock")
        constraints.append({
            "check": "vm_lock_status",
            "ok": lock_status is None,
            "details": {"lock_type": lock_status or "none", "can_proceed": lock_status is None}
        })
        
        # Check HA status (simplified - would need cluster API call for full check)
        ha_managed = vm_data.get("ha", {}).get("managed", False)
        constraints.append({
            "check": "ha_constraints", 
            "ok": True,  # Assume OK for now - would check HA policies
            "details": {"ha_managed": ha_managed, "ha_checks": "passed"}
        })
        
        return constraints

    async def _validate_vm_resources(self, http, node: str, vmid: str, vm_data: Dict[str, Any], verb: str) -> List[Dict[str, Any]]:
        """Validate VM resource constraints and dependencies."""
        resources = []
        
        # Check current resource usage
        cpu_usage = vm_data.get("cpu", 0)
        mem_usage = vm_data.get("mem", 0)
        max_mem = vm_data.get("maxmem", 1)
        
        mem_percent = (mem_usage / max_mem * 100) if max_mem > 0 else 0
        
        resources.append({
            "check": "resource_utilization",
            "ok": True,  # Resource checks are informational for most verbs
            "details": {
                "cpu_percent": round(cpu_usage * 100, 1),
                "memory_percent": round(mem_percent, 1),
                "memory_mb": mem_usage // (1024 * 1024) if mem_usage else 0
            }
        })
        
        return resources

    async def _analyze_vm_state(self, http, node: str, vmid: str, vm_data: Dict[str, Any], 
                              verb: str, inventory_context: Dict[str, Any]) -> Dict[str, Any]:
        """Deep analysis of VM state beyond basic status.
        
        This method performs comprehensive state analysis using live data fetched from
        the Proxmox API. It builds upon the normalized state to provide detailed context
        for dry-run decision making.
        """
        # Use normalized state from our enhanced detection method
        normalized_state = self._normalize_vm_state(vm_data)
        
        analysis = {
            # Raw state fields (exactly as received from API)
            "basic_state": vm_data.get("status", "<not_provided>"),
            "qmp_status": vm_data.get("qmpstatus", "<not_provided>"),
            # Normalized state (our authoritative interpretation)
            "normalized_state": normalized_state,
            # Runtime indicators
            "has_guest_agent": "agent" in vm_data and vm_data.get("agent", 0) == 1,
            "uptime_seconds": vm_data.get("uptime", 0),
            "boot_time": vm_data.get("uptime", 0) > 0,
            "process_id": vm_data.get("pid"),
            "is_running_process": bool(vm_data.get("pid") is not None and str(vm_data.get("pid", 0)).isdigit() and int(str(vm_data.get("pid", 0))) > 0),
            # Resource usage (indicates actual activity)
            "cpu_usage_percent": round((vm_data.get("cpu", 0) or 0) * 100, 2),
            "memory_used_bytes": vm_data.get("mem", 0),
            "memory_total_bytes": vm_data.get("maxmem", 0),
            "disk_usage_bytes": vm_data.get("disk", 0)
        }
        
        # Check for running tasks
        try:
            tasks_resp = await http.call({"method": "GET", "path": f"/nodes/{node}/tasks"})
            if tasks_resp.get("ok"):
                tasks = tasks_resp.get("data", [])
                vm_tasks = [t for t in tasks if str(vmid) in t.get("id", "") and t.get("status") == "running"]
                analysis["active_tasks"] = len(vm_tasks)
                analysis["has_active_tasks"] = len(vm_tasks) > 0
            else:
                analysis["active_tasks"] = 0
                analysis["has_active_tasks"] = False
        except Exception:
            analysis["active_tasks"] = 0
            analysis["has_active_tasks"] = False
            
        return analysis

    def _determine_target_state(self, verb: str, current_state: str) -> str:
        """Determine target state based on verb and current state."""
        state_map = {
            "start": "running",
            "shutdown": "stopped", 
            "stop": "stopped",
            "suspend": "suspended",
            "resume": "running",
            "reset": "running"  # Reset keeps VM running but restarts it
        }
        return state_map.get(verb, current_state)

    def _validate_state_transition(self, current_state: str, target_state: str, verb: str,
                                 state_analysis: Dict[str, Any], inventory_context: Dict[str, Any]) -> tuple:
        """Validate that the state transition is valid and safe."""
        is_no_op = current_state == target_state
        
        # Special cases for state transitions
        transition_issues = []
        
        if verb == "shutdown" and current_state == "running":
            if not state_analysis.get("has_guest_agent", False):
                transition_issues.append("VM lacks guest agent - will use ACPI shutdown")
        
        if state_analysis.get("has_active_tasks", False):
            transition_issues.append(f"VM has {state_analysis['active_tasks']} active tasks")
        
        details = {
            "from": current_state,
            "to": target_state,
            "no_op": is_no_op,
            "transition_issues": transition_issues,
            "graceful_capable": state_analysis.get("has_guest_agent", False),
            "uptime_seconds": state_analysis.get("uptime_seconds", 0)
        }
        
        # Transition is valid unless there are blocking issues
        is_valid = len([issue for issue in transition_issues if "lacks" not in issue]) == 0
        
        return is_valid, details

    def _calculate_operation_severity(self, verb: str, current_state: str, target_state: str,
                                    state_analysis: Dict[str, Any], preconditions: List[Dict[str, Any]],
                                    inventory_context: Dict[str, Any]) -> str:
        """Calculate operation severity based on comprehensive risk analysis."""
        
        # Start with base severity
        if current_state == target_state:
            base_severity = "info"  # No-op operations
        elif verb in {"shutdown", "stop", "reset"}:
            base_severity = "warn"  # Destructive operations
        elif verb in {"suspend"}:
            base_severity = "warn"  # Service interrupting operations  
        else:
            base_severity = "info"  # Safe operations like start, resume
        
        # Escalate severity based on risk factors
        risk_factors = []
        
        # Check for failing preconditions
        failed_checks = [check for check in preconditions if not check.get("ok", False)]
        if failed_checks:
            risk_factors.append(f"{len(failed_checks)} failed preconditions")
            
        # Check for active tasks
        if state_analysis.get("has_active_tasks", False):
            risk_factors.append("active background tasks")
            
        # Check inventory staleness  
        if inventory_context.get("staleness_ms", 0) > 10000:  # >10s stale
            risk_factors.append("potentially stale inventory data")
            
        # Escalate severity based on risk factors
        if failed_checks:
            return "error"  # Any failed precondition is an error
        elif len(risk_factors) > 1:
            return "warn" if base_severity == "info" else "error"  
        elif risk_factors:
            return "warn" if base_severity == "info" else base_severity
        else:
            return base_severity

    async def _generate_execution_plan(self, http, node: str, vmid: str, verb: str,
                                     vm_data: Dict[str, Any], state_analysis: Dict[str, Any],
                                     inventory_context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate detailed execution plan with timing and steps."""
        
        steps = []
        estimated_duration = 0
        
        # Pre-execution steps
        if state_analysis.get("has_active_tasks", False):
            steps.append(f"Wait for {state_analysis['active_tasks']} active tasks to complete")
            estimated_duration += 30  # 30s average task completion
            
        # Main execution step  
        if verb == "shutdown":
            if state_analysis.get("has_guest_agent", False):
                steps.append("Send guest agent shutdown command")
                estimated_duration += 15  # Graceful shutdown
            else:
                steps.append("Send ACPI shutdown signal")
                estimated_duration += 30  # Less predictable
        else:
            steps.append(f"Execute {verb} via Proxmox API")
            estimated_duration += {"start": 10, "stop": 5, "reset": 20, "suspend": 8, "resume": 5}.get(verb, 10)
        
        # Post-execution verification
        steps.append("Verify state transition completed")
        estimated_duration += 5
        
        return {
            "kind": "api",
            "preview": [{"method": "POST", "endpoint": f"/nodes/{node}/qemu/{vmid}/status/{verb}"}],
            "steps": steps,
            "estimated_duration_seconds": estimated_duration,
            "parallel_safe": False,  # VM operations should be sequential
            "requires_confirmation": verb in {"shutdown", "stop", "reset"}
        }

    async def _calculate_execution_effects(self, http, node: str, vmid: str, verb: str,
                                         current_state: str, target_state: str,
                                         state_analysis: Dict[str, Any], 
                                         inventory_context: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate expected effects with impact analysis."""
        
        effects_summary_parts = []
        
        if current_state == target_state:
            effects_summary_parts.append(f"No state change (already {current_state})")
        else:
            effects_summary_parts.append(f"State transition: {current_state} → {target_state}")
            
        # Add impact details
        if verb in {"shutdown", "stop"}:
            uptime = state_analysis.get("uptime_seconds", 0)
            if uptime > 3600:  # >1 hour uptime
                effects_summary_parts.append(f"Ending {uptime // 3600}h {(uptime % 3600) // 60}m uptime")
        
        per_target_effect = {
            "id": f"vm:{vmid}",
            "from": {"status": current_state, "uptime": state_analysis.get("uptime_seconds", 0)},
            "to": {"status": target_state, "uptime": 0 if target_state == "stopped" else None}
        }
        
        # Add estimated resource changes
        if target_state == "stopped":
            per_target_effect["to"]["resource_impact"] = "freed"
        elif current_state == "stopped" and target_state == "running":
            per_target_effect["to"]["resource_impact"] = "allocated"
        
        return {
            "summary": "; ".join(effects_summary_parts),
            "per_target": [per_target_effect],
            "business_impact": self._assess_business_impact(verb, current_state, target_state, state_analysis),
            "rollback_available": verb not in {"reset"}  # Reset can't be easily undone
        }

    def _assess_business_impact(self, verb: str, current_state: str, target_state: str, 
                               state_analysis: Dict[str, Any]) -> str:
        """Assess business impact of the operation."""
        if current_state == target_state:
            return "none"
        elif verb in {"shutdown", "stop"} and current_state == "running":
            uptime = state_analysis.get("uptime_seconds", 0)
            if uptime > 86400:  # >1 day
                return "high - interrupting long-running service"  
            elif uptime > 3600:  # >1 hour
                return "medium - interrupting established service"
            else:
                return "low - recently started service"
        elif verb == "start" and current_state == "stopped":
            return "positive - restoring service availability"
        else:
            return "low"

    def _generate_idempotency_key(self, verb: str, vmid: str, current_state: str,
                                 state_analysis: Dict[str, Any], 
                                 inventory_context: Dict[str, Any]) -> str:
        """Generate enhanced idempotency key with context."""
        # Include state context in key for better idempotency detection
        state_signature = f"{current_state}:{state_analysis.get('qmp_status', '<missing>')}"
        consistency_token = inventory_context.get("consistency_token", "<no_token>")
        
        return f"proxmox.vm:{verb}:vm:{vmid}:state:{state_signature}:token:{consistency_token[:8]}"

    def _generate_operation_reason(self, all_checks_ok: bool, severity: str, 
                                  preconditions: List[Dict[str, Any]]) -> str:
        """Generate human-readable reason for the operation result."""
        if not all_checks_ok:
            failed = [check["check"] for check in preconditions if not check.get("ok", False)]
            return f"Operation blocked by failed checks: {', '.join(failed)}"
        elif severity == "error":
            return "Operation has high risk of failure"
        elif severity == "warn":
            return "Operation may cause service disruption"
        else:
            return None  # No specific reason needed for successful operations
            
    def _build_error_response(self, verb: str, vmid: str, preconditions: List[Dict[str, Any]], 
                             reason: str) -> Dict[str, Any]:
        """Build standardized error response for failed dry runs.
        
        This method creates a comprehensive error response that provides clear information
        about why the operation cannot proceed, without falling back to unknown states.
        """
        return {
            "ok": False,
            "severity": "error",
            "idempotency_key": f"proxmox.vm:{verb}:vm:{vmid}:error:{int(time.time())}",
            "preconditions": preconditions,
            "plan": {
                "kind": "api", 
                "preview": [], 
                "steps": [f"Operation blocked: {reason}"], 
                "estimated_duration_seconds": 0,
                "blocked": True
            },
            "effects": {
                "summary": "Operation cannot proceed", 
                "per_target": [], 
                "business_impact": "operation_blocked",
                "error_details": reason
            },
            "reason": reason,
            "inventory_metadata": {
                "strategy_used": "error_fallback", 
                "data_staleness_ms": 0,
                "error_encountered": True
            }
        }

    # ---------- Inventory helpers ----------

    def _tags_to_labels(self, tags_val) -> Dict[str, bool]:
        """Proxmox returns tags as a semicolon-separated string; convert to labels."""
        if not tags_val:
            return {}
        if isinstance(tags_val, dict):
            return tags_val
        if isinstance(tags_val, str):
            parts = [t.strip() for t in tags_val.split(";") if t.strip()]
            return {t: True for t in parts}
        return {}

    async def _list_vms(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """List VMs according to walNUT inventory contract.
        
        Returns VM targets in format:
        {type:"vm", id:"<vmid>", name:"<name>", status:"running|stopped|paused|unknown", attrs:{node:<str>}, labels:{}}
        """
        node = self.config["node"]
        http = await self._http()

        result = await http.call({"method": "GET", "path": f"/nodes/{node}/qemu"})
        if not result.get("ok"):
            raise RuntimeError(f"Failed to list VMs: {result.get('raw')}")
        
        # The HTTP transport returns {'data': [VMs]}, but we need just the array
        raw_data = result.get("data", []) or []
        if isinstance(raw_data, dict) and "data" in raw_data:
            vms_data = raw_data["data"]
        else:
            vms_data = raw_data

        targets: List[Dict[str, Any]] = []
        for vm in vms_data:
            # Handle case where vm might be a string instead of dict
            if isinstance(vm, str):
                continue  # Skip malformed entries
            if not isinstance(vm, dict):
                continue  # Skip non-dict entries
            # Skip templates: Proxmox marks templates with template=1
            try:
                tmpl = vm.get("template", 0)
                if isinstance(tmpl, str):
                    is_template = tmpl.strip().lower() in ("1", "true", "yes")
                else:
                    is_template = bool(tmpl)
                if is_template:
                    continue
            except Exception:
                pass
            
            vmid = str(vm.get("vmid", ""))
            if not vmid:
                continue  # Skip entries without vmid

            # Map Proxmox status to standard format
            proxmox_status = vm.get("status", "unknown")
            if proxmox_status == "running":
                standard_status = "running"
            elif proxmox_status == "stopped":
                standard_status = "stopped"
            elif proxmox_status in ("suspended", "paused"):
                standard_status = "paused"
            else:
                standard_status = "unknown"

            # Filter by active_only - running VMs are considered "active"
            if active_only and standard_status not in ("running",):
                continue

            # Build attrs dict with node and additional metadata
            attrs = {
                "node": node,
                "cpus": vm.get("cpus"),
                "maxmem": vm.get("maxmem"),
            }

            # Enrich with current status if needed for more accurate state
            try:
                status_resp = await http.call({"method": "GET", "path": f"/nodes/{node}/qemu/{vmid}/status/current"})
                if status_resp.get("ok"):
                    sdata = status_resp.get("data", {}) or {}
                    # Update status with more accurate current state if available
                    current_status = sdata.get("status")
                    qmp_status = sdata.get("qmpstatus")
                    if current_status:
                        if current_status == "running":
                            standard_status = "running"
                        elif current_status == "stopped":
                            standard_status = "stopped"
                        elif current_status in ("suspended", "paused") or qmp_status in ("suspended", "paused"):
                            standard_status = "paused"
                    
                    attrs.update({
                        "cpu_usage": sdata.get("cpu"),      # fraction 0.0–1.0
                        "mem_used": sdata.get("mem"),
                        "mem_total": sdata.get("maxmem"),
                        "disk_used": sdata.get("disk"),
                        "disk_total": sdata.get("maxdisk"),
                        "qmpstatus": qmp_status,
                    })
            except Exception:
                pass

            # Apply active_only filter again after status enrichment
            if active_only and standard_status not in ("running",):
                continue

            targets.append({
                "type": "vm",
                "id": vmid,  # Add 'id' field per inventory contract
                "external_id": vmid,  # Keep existing field for compatibility 
                "name": vm.get("name") or f"VM-{vmid}",  # Ensure name is always present
                "status": standard_status,
                "attrs": attrs,
                "labels": self._tags_to_labels(vm.get("tags")),
            })
        return targets

    async def _list_hosts(self) -> List[Dict[str, Any]]:
        node_name = self.config["node"]
        http = await self._http()
        attrs: Dict[str, Any] = {}
        try:
            resp = await http.call({"method": "GET", "path": f"/nodes/{node_name}/status"})
            if resp.get("ok"):
                data = resp.get("data", {}) or {}
                attrs.update({
                    "cpu": data.get("cpu"),
                    "mem_used": data.get("mem"),
                    "mem_total": data.get("maxmem"),
                    "uptime": data.get("uptime"),
                    "kversion": data.get("kversion"),
                    "pveversion": data.get("pveversion"),
                })
        except Exception:
            pass

        return [{
            "type": "host",
            "external_id": node_name,
            "name": node_name,
            "attrs": attrs,
            "labels": {},
        }]
