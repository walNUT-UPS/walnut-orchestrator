import pytest
pytest.skip("Integration driver test skipped by default; requires environment and network mocks", allow_module_level=True)
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
import yaml

from walnut.core.manifests import ManifestLoader, IntegrationManifest
from walnut.core.registry import get_driver
from walnut.database.models import IntegrationType, IntegrationInstance

# A simple class to stand in for the DB model for tests
class Target:
    def __init__(self, type, external_id, name, attrs=None, labels=None):
        self.type = type
        self.external_id = external_id
        self.name = name
        self.attrs = attrs or {}
        self.labels = labels or {}

INTEGRATIONS_DIR = Path(__file__).parent.parent / "integrations"

@pytest.fixture
def proxmox_manifest_info():
    """Loads the Proxmox manifest and its path for testing."""
    loader = ManifestLoader(INTEGRATIONS_DIR)
    manifests = loader.load_all()
    proxmox_manifest_info = next((m for m in manifests if m["manifest"].id == "walnut.proxmox.ve"), None)
    assert proxmox_manifest_info is not None
    return proxmox_manifest_info

def test_load_proxmox_manifest(proxmox_manifest_info):
    """Tests that the Proxmox manifest is loaded and parsed correctly."""
    manifest = proxmox_manifest_info["manifest"]
    assert manifest.id == "walnut.proxmox.ve"
    assert manifest.name == "Proxmox VE"
    assert manifest.driver.entrypoint == "driver:ProxmoxVeDriver"
    assert len(manifest.capabilities) == 3

@pytest.fixture
def proxmox_driver(proxmox_manifest_info):
    """Creates an instance of the Proxmox driver for testing."""
    manifest = proxmox_manifest_info["manifest"]
    driver_path = proxmox_manifest_info["path"] / "driver.py"

    type_model = IntegrationType(
        name=manifest.id,
        version=manifest.version,
        min_core_version=manifest.min_core_version,
        manifest_yaml=yaml.dump(manifest.dict()),
        capabilities=[cap.dict() for cap in manifest.capabilities],
        driver_path=str(driver_path),
        driver_entrypoint=manifest.driver.entrypoint,
    )

    config = {
        "host": "pve.example.com",
        "port": 8006,
        "node": "pve-node-1",
    }
    instance_model = IntegrationInstance(
        id=1,
        type_id=1,
        name="pve-test-instance",
        display_name="PVE Test Instance",
        config=config,
    )
    instance_model.type = type_model

    secrets = {"api_token": "test-token"}

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        driver = get_driver(instance_model, secrets)
        driver.client = mock_client_instance
        yield driver

@pytest.mark.asyncio
async def test_driver_test_connection(proxmox_driver):
    """Tests the structured output of the test_connection method."""
    mock_response = AsyncMock()
    # Mock the return value of the async json() method
    mock_response.json = AsyncMock(return_value={"data": {"version": "8.2-2"}})
    # Make raise_for_status a simple function that does nothing
    mock_response.raise_for_status = lambda: None
    proxmox_driver.client.get.return_value = mock_response

    result = await proxmox_driver.test_connection()

    assert result["status"] == "connected"
    assert result["version"] == "8.2-2"
    assert "latency_ms" in result

@pytest.mark.asyncio
async def test_driver_inventory_list_vms(proxmox_driver):
    """Tests the inventory_list method for VMs."""
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={
        "data": [
            {"vmid": 100, "name": "vm1", "status": "running", "cpus": 2, "maxmem": 2048, "tags": "test,prod"},
            {"vmid": 101, "name": "vm2", "status": "stopped", "cpus": 4, "maxmem": 4096},
        ]
    })
    mock_response.raise_for_status = lambda: None
    proxmox_driver.client.get.return_value = mock_response

    targets = await proxmox_driver.inventory_list(target_type="vm", dry_run=False)

    assert len(targets) == 2
    assert targets[0]["external_id"] == "100"
    assert targets[1]["name"] == "vm2"

@pytest.mark.asyncio
async def test_driver_vm_lifecycle_dry_run(proxmox_driver):
    """Tests the structured dry-run output for the vm_lifecycle method."""
    target = Target(type="vm", external_id="101", name="vm2")

    result = await proxmox_driver.vm_lifecycle(verb="shutdown", target=target, dry_run=True)

    assert result["will_call"][0]["method"] == "POST"
    assert "pve-node-1/qemu/101/status/shutdown" in result["will_call"][0]["path"]
    assert result["expected_effect"]["target"]["id"] == "101"
    assert result["risk"] == "low"
