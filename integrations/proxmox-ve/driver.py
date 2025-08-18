"""
Proxmox VE Integration Driver.
"""
import time
from typing import Dict, Any, Optional, List

import httpx

# The core will pass Target and IntegrationInstance objects.
# The driver does not need to define them.

class ProxmoxVeDriver:
    """
    Driver for interacting with the Proxmox VE API.
    """

    def __init__(self, instance, secrets: Dict[str, str]):
        self.instance = instance
        self.config = instance.config
        self.secrets = secrets

        self.base_url = f"https://{self.config['host']}:{self.config['port']}/api2/json"
        api_token = self.secrets.get("api_token")
        if not api_token:
            raise ValueError("Proxmox API token is missing.")

        self.client = httpx.AsyncClient(
            verify=self.config.get("verify_ssl", True),
            headers={
                "Authorization": f"PVEAPIToken={api_token}",
                "Accept": "application/json",
            }
        )

    async def test_connection(self) -> Dict[str, Any]:
        """
        Tests connectivity by fetching the Proxmox server version.
        """
        start_time = time.monotonic()
        try:
            response = await self.client.get(f"{self.base_url}/version")
            response.raise_for_status()
            data = await response.json()
            data = data.get('data', {})
            latency_ms = int((time.monotonic() - start_time) * 1000)
            return {
                "status": "connected",
                "latency_ms": latency_ms,
                "version": data.get('version'),
            }
        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            return {"status": "error", "message": str(e), "latency_ms": latency_ms}

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

    async def vm_lifecycle(self, verb: str, target, dry_run: bool) -> Dict[str, Any]:
        """Handles all vm.lifecycle actions."""
        node = self.config['node']
        vmid = target.external_id
        url = f"{self.base_url}/nodes/{node}/qemu/{vmid}/status/{verb}"

        if dry_run:
            return {
                "will_call": [{"method": "POST", "path": url}],
                "expected_effect": {
                    "target": {"type": "vm", "id": vmid},
                    "state_change": f"unknown -> {verb}"
                },
                "assumptions": ["vm.exists", "auth.token.valid"],
                "risk": "low"
            }

        response = await self.client.post(url)
        response.raise_for_status()
        return {"task_id": (await response.json()).get('data')}

    async def power_control(self, verb: str, target, dry_run: bool) -> Dict[str, Any]:
        """Handles power.control actions for the host."""
        node = self.config['node']
        if target.external_id != node:
            raise ValueError(f"Target {target.external_id} does not match configured node {node}.")

        url = f"{self.base_url}/nodes/{node}/status"

        if verb == "shutdown":
            if dry_run:
                return {
                    "will_call": [{"method": "POST", "path": url, "data": {"command": "shutdown"}}],
                    "expected_effect": {
                        "target": {"type": "host", "id": node},
                        "state_change": "running -> stopped"
                    },
                    "assumptions": ["host.exists"],
                    "risk": "high"
                }
            return {"message": "Simulated host shutdown."}

        elif verb == "cycle":
            if dry_run:
                return {
                    "will_call": [
                        {"method": "POST", "path": url, "data": {"command": "shutdown"}},
                        {"method": "ACTION", "type": "wait", "duration_s": 60},
                        {"message": "Node start is manual after shutdown."}
                    ],
                    "expected_effect": {
                        "target": {"type": "host", "id": node},
                        "state_change": "running -> running"
                    },
                    "risk": "high"
                }
            return {"message": "Host cycle is not implemented."}

        raise ValueError(f"Unsupported verb for host power.control: {verb}")

    async def _list_vms(self) -> List[Dict[str, Any]]:
        """Helper to list VMs."""
        node = self.config['node']
        response = await self.client.get(f"{self.base_url}/nodes/{node}/qemu")
        response.raise_for_status()
        vms_data = (await response.json()).get('data', [])

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
        return [{
            "type": "host", "external_id": node_name, "name": node_name, "attrs": {}, "labels": {},
        }]
