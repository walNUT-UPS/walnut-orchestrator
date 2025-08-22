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
    Implements:
      - test_connection(): GET /version (+ optional node status)
      - heartbeat(): GET /nodes/{node}/status (+ VM counts)
      - inventory.list: host metrics + VM metrics (status/current)
      - vm.lifecycle: start/stop/shutdown/suspend/resume/reset (plan-based)
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
                return {"status": "error", "message": message, "latency_ms": latency_ms}

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
                "latency_ms": latency_ms,
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

                return {"state": "connected", "latency_ms": latency_ms, "metrics": metrics}

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

    async def inventory_list(self, target_type: str, dry_run: bool) -> List[Dict[str, Any]]:
        if dry_run:
            return [{"dry_run_message": f"Would list all targets of type {target_type}"}]
        if target_type == "vm":
            return await self._list_vms()
        if target_type == "host":
            return await self._list_hosts()
        raise ValueError(f"Unsupported target_type for inventory.list: {target_type}")

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
        node = self.config["node"]
        vmid = target.external_id
        valid = {"start", "stop", "shutdown", "suspend", "resume", "reset"}
        if verb not in valid:
            raise ValueError(f"Unsupported vm.lifecycle verb: {verb}")

        path = f"/nodes/{node}/qemu/{vmid}/status/{verb}"
        plan = {"steps": [{"type": "http.request", "request": {"method": "POST", "path": path}}]}

        if dry_run:
            return {
                "dry_run": True,
                "plan": plan,
                "expected_effect": {"target": {"type": "vm", "id": vmid}, "state_change": f"unknown -> {verb}"},
                "assumptions": ["vm.exists", "auth.token.valid"],
                "risk": "low",
            }

        result = await self._execute_plan(plan)
        if not result.get("ok"):
            raise RuntimeError(f"API call to {path} failed: {result.get('raw')}")
        return {"task_id": (result.get("data") or {}).get("data")}

    async def power_control(self, verb: str, target, dry_run: bool) -> Dict[str, Any]:
        node = self.config["node"]
        if target.external_id != node:
            raise ValueError(f"Target {target.external_id} does not match configured node {node}.")

        # Proxmox supports POST /nodes/{node}/status with {command: 'shutdown'|'reboot'}
        path = f"/nodes/{node}/status"
        if verb not in {"shutdown", "cycle"}:
            raise ValueError(f"Unsupported verb for host power.control: {verb}")

        if dry_run:
            cmd = "reboot" if verb == "cycle" else "shutdown"
            return {
                "will_call": [{"transport": "http", "method": "POST", "path": path, "data": {"command": cmd}}],
                "expected_effect": {
                    "target": {"type": "host", "id": node},
                    "state_change": "running -> restarting" if verb == "cycle" else "running -> stopped",
                },
                "assumptions": ["host.exists"],
                "risk": "high",
            }

        # Execution is simulated (actual reboot/shutdown requires elevated perms).
        return {"message": "Simulated host power action via API.", "verb": verb}

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

    async def _list_vms(self) -> List[Dict[str, Any]]:
        node = self.config["node"]
        http = await self._http()

        result = await http.call({"method": "GET", "path": f"/nodes/{node}/qemu"})
        if not result.get("ok"):
            raise RuntimeError(f"Failed to list VMs: {result.get('raw')}")
        vms_data = result.get("data", []) or []

        targets: List[Dict[str, Any]] = []
        for vm in vms_data:
            vmid = str(vm.get("vmid"))
            attrs = {
                "status": vm.get("status"),
                "cpus": vm.get("cpus"),
                "maxmem": vm.get("maxmem"),
            }

            # Enrich with current status
            try:
                status_resp = await http.call({"method": "GET", "path": f"/nodes/{node}/qemu/{vmid}/status/current"})
                if status_resp.get("ok"):
                    sdata = status_resp.get("data", {}) or {}
                    attrs.update({
                        "cpu_usage": sdata.get("cpu"),      # fraction 0.0–1.0
                        "mem_used": sdata.get("mem"),
                        "mem_total": sdata.get("maxmem"),
                        "disk_used": sdata.get("disk"),
                        "disk_total": sdata.get("maxdisk"),
                        "qmpstatus": sdata.get("qmpstatus"),
                    })
            except Exception:
                pass

            targets.append({
                "type": "vm",
                "external_id": vmid,
                "name": vm.get("name"),
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