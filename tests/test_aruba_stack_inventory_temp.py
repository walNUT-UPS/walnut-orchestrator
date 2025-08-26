import types
import pytest


@pytest.mark.asyncio
async def test_aruba_inventory_list_stack_members(monkeypatch):
    # Ensure repo root is importable
    import importlib, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    # Load driver module by file path (folder name has dots)
    import importlib.util
    driver_path = root / 'integrations' / 'com.aruba.aoss' / 'driver.py'
    spec = importlib.util.spec_from_file_location('aoss_driver_test', str(driver_path))
    assert spec and spec.loader
    driver_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver_mod)  # type: ignore[attr-defined]

    # Fake instance and transports
    class DummyInstance:
        def __init__(self):
            self.type_id = 'com.aruba.aoss'
            self.name = 'test-switch'
            self.config = {
                'hostname': '1.2.3.4',
                'username': 'u',
                # optional fields consumed by _build_connection_dict
                'ssh_port': 22,
                'timeout_s': 5,
            }

    class DummyTransports:
        async def get(self, *_args, **_kwargs):
            return None
        async def close_all(self):
            return None

    instance = DummyInstance()
    secrets = {'password': 'x', 'snmp_community': 'public'}
    transports = DummyTransports()

    # Monkeypatch stack info to avoid real SSH
    def fake_get_stack_info(connection: dict) -> dict:
        return {
            'members': [
                {'id': '1', 'model': '2930F', 'status': 'active', 'priority': 1, 'role': 'master'},
                {'id': '2', 'model': '2930F', 'status': 'active', 'priority': 2, 'role': 'member'},
            ]
        }

    monkeypatch.setattr(driver_mod, '_get_stack_info', fake_get_stack_info)

    drv = driver_mod.ArubaOSSwitchDriver(instance=instance, secrets=secrets, transports=transports)

    items = await drv.inventory_list('stack_member', active_only=True)
    assert isinstance(items, list)
    # Should return two stack members with normalized fields
    assert len(items) == 2
    assert items[0]['type'] == 'stack_member'
    assert items[0]['id'] == '1' and items[0]['external_id'] == '1'
