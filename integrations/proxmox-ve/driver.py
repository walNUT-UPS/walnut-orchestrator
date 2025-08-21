"""
Proxmox VE Integration Driver (Refactored for Transports).
"""
from typing import Dict, Any, Optional, List

# The core will pass Target, IntegrationInstance, and TransportManager objects.
# The driver does not need to define them.

class ProxmoxVeDriver:
    """
    Driver for interacting with the Proxmox VE API using the transport layer.
    """

    def __init__(self, instance, secrets: Dict[str, str], transports):
        self.instance = instance
        self.config = instance.config
        self.secrets = secrets
        self.transports = transports

        # The API token is now configured into the transport's headers
        # during the 'prepare' phase, which is handled by the TransportManager.
        # We just need to ensure the config is shaped correctly.
        api_token = self.secrets.get("api_token")
        if not api_token:
            raise ValueError("Proxmox API token is missing from secrets.")

        # This driver assumes the http transport will be configured with
        # the base_url and necessary headers. The TransportManager will find
        # these keys in the instance config.
        self.config["base_url"] = f"https://{self.config.get('host')}:{self.config.get('port')}/api2/json"
        self.config["headers"] = {
            "Authorization": f"PVEAPIToken={api_token}",
            "Accept": "application/json",
        }

    async def test_connection(self) -> Dict[str, Any]:
        """
        Tests connectivity by fetching the Proxmox server version via the http transport.
        """
        try:
            # The transport manager will prepare the http adapter with the config
            # from the __init__ method.
            http = await self.transports.get('http')
            result = await http.call({"method": "GET", "path": "/version"})

            if not result.get("ok"):
                return {"status": "error", "message": result.get("raw", "request failed"), "latency_ms": result.get("latency_ms")}

            data = result.get('data', {})
            return {
                "status": "connected",
                "latency_ms": result.get("latency_ms"),
                "version": data.get('version'),
                "details": data
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def inventory_list(self, target_type: str, dry_run: bool) -> List[Dict[str, Any]]:
        """Handles the 'inventory.list' capability."""
        if dry_run:
            return [{"dry_run_message": f"Would list all targets of type {target_type}"}]

        if target_type == 'vm':
            return await self._list_vms()
        elif target_type == 'host':
            return await self._list_hosts()
        else:
            raise ValueError(f"Unsupported target_type for inventory.list: {target_type}")

    async def _execute_plan(self, plan: dict, dry_run: bool = False):
        """
        A simple plan executor. For non-dry-run, it executes the first step.
        A more advanced executor could handle dependencies and multiple steps.
        """
        if dry_run:
            # For dry runs, we just return the plan itself, enriched.
            plan["dry_run"] = True
            return plan

        if not plan or not plan.get("steps"):
            raise ValueError("Invalid plan provided for execution.")

        # Execute the first step
        step = plan["steps"][0]
        transport_type, _ = step["type"].split(".", 1)
        request = step["request"]

        transport = await self.transports.get(transport_type)
        return await transport.call(request)

    async def vm_lifecycle(self, verb: str, target, dry_run: bool) -> Dict[str, Any]:
        """Handles all vm.lifecycle actions using a plan-based approach."""
        node = self.config['node']
        vmid = target.external_id
        path = f"/nodes/{node}/qemu/{vmid}/status/{verb}"

        # 1. Define the plan
        plan = {
            "steps": [{"type": "http.request", "request": {"method": "POST", "path": path}}]
        }

        # 2. For dry-run, enrich and return the plan
        if dry_run:
            return {
                "dry_run": True,
                "plan": plan,
                "expected_effect": {
                    "target": {"type": "vm", "id": vmid},
                    "state_change": f"unknown -> {verb}"
                },
                "assumptions": ["vm.exists", "auth.token.valid"],
                "risk": "low"
            }

        # 3. For execution, run the plan
        result = await self._execute_plan(plan)

        if not result.get("ok"):
            raise RuntimeError(f"API call to {path} failed: {result.get('raw')}")

        return {"task_id": result.get('data', {}).get('data')}

    async def power_control(self, verb: str, target, dry_run: bool) -> Dict[str, Any]:
        """Handles power.control actions for the host."""
        # This is a sample, so we won't implement the actual power control logic
        # as it's often complex (e.g. requires IPMI or a different endpoint).
        node = self.config['node']
        if target.external_id != node:
            raise ValueError(f"Target {target.external_id} does not match configured node {node}.")

        path = f"/nodes/{node}/status"

        if verb == "shutdown":
            if dry_run:
                return {
                    "will_call": [{"transport": "http", "method": "POST", "path": path, "data": {"command": "shutdown"}}],
                    "expected_effect": {"target": {"type": "host", "id": node}, "state_change": "running -> stopped"},
                    "assumptions": ["host.exists"],
                    "risk": "high"
                }
            return {"message": "Simulated host shutdown via API."}

        raise ValueError(f"Unsupported verb for host power.control: {verb}")

    async def _list_vms(self) -> List[Dict[str, Any]]:
        """Helper to list VMs using the http transport."""
        node = self.config['node']
        http = await self.transports.get('http')
        result = await http.call({"method": "GET", "path": f"/nodes/{node}/qemu"})

        if not result.get("ok"):
            raise RuntimeError(f"Failed to list VMs: {result.get('raw')}")

        vms_data = result.get('data', [])
        targets = [
            {
                "type": "vm",
                "external_id": str(vm['vmid']),
                "name": vm['name'],
                "attrs": {"status": vm['status'], "cpus": vm['cpus'], "maxmem": vm['maxmem']},
                "labels": vm.get('tags', {}),
            }
            for vm in vms_data
        ]
        return targets

    async def _list_hosts(self) -> List[Dict[str, Any]]:
        """Helper to list the configured host."""
        node_name = self.config['node']
        return [{"type": "host", "external_id": node_name, "name": node_name, "attrs": {}, "labels": {}}]
