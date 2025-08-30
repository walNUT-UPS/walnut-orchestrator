import os
from pathlib import Path
import pytest
pytest.skip("E2E API test skipped by default; relies on DB + plugins", allow_module_level=True)
import anyio


@pytest.mark.asyncio
async def test_hosts_inventory_stack_member_host2(async_client):
    """E2E API call: GET /api/hosts/2/inventory?type=stack_member

    Seeds the DB with an Aruba AOS-S integration instance id=2 and monkeypatches
    the integrations inventory fetcher to return fake stack members.
    """
    # Seed DB: integration type + instance id=2
    from walnut.database.connection import get_db_session
    from walnut.database.models import IntegrationType, IntegrationInstance, IntegrationSecret

    integrations_root = (Path(__file__).resolve().parents[1] / 'integrations' / 'com.aruba.aoss').resolve()
    assert integrations_root.exists(), f"Integration path missing: {integrations_root}"

    async with get_db_session() as session:
        # Upsert type
        type_id = 'com.aruba.aoss'
        type_obj = IntegrationType(
            id=type_id,
            name='ArubaOS-S Switches',
            version='0.1.0',
            min_core_version='0.10.0',
            category='network-device',
            path=str(integrations_root),
            status='valid',
            capabilities={'list': []},
            schema_connection={'type': 'object', 'properties': {}},
            defaults={},
            test_config={},
            driver_entrypoint='driver:ArubaOSSwitchDriver',
        )
        # delete existing if any, then add (SQLite upsert-lite)
        try:
            await anyio.to_thread.run_sync(session.merge, type_obj)
        except Exception:
            pass

        # Instance id=2
        inst = IntegrationInstance(
            instance_id=2,
            type_id=type_id,
            name='test-switch',
            config={
                'hostname': '1.2.3.4',
                'username': 'admin',
                'ssh_port': 22,
                'timeout_s': 5,
            },
            state='configured',
        )
        await anyio.to_thread.run_sync(session.merge, inst)

        # Minimal secrets required by driver
        for field, value in (('password', 'x'), ('snmp_community', 'public')):
            sec = IntegrationSecret(instance_id=2, field_name=field, secret_type='string', encrypted_value=value.encode('utf-8'))
            await anyio.to_thread.run_sync(session.merge, sec)

    # Monkeypatch integrations inventory fetcher to return two stack members
    from walnut.api import integrations as integrations_api

    async def fake_get_cached_inventory(session, instance, target_type: str, active_only: bool, force_refresh: bool = False):
        assert instance.instance_id == 2
        assert target_type == 'stack_member'
        return [
            { 'type': 'stack_member', 'id': '1', 'external_id': '1', 'name': 'Member 1', 'attrs': {}, 'labels': {} },
            { 'type': 'stack_member', 'id': '2', 'external_id': '2', 'name': 'Member 2', 'attrs': {}, 'labels': {} },
        ]

    # Patch and call API
    orig = integrations_api._get_cached_inventory
    integrations_api._get_cached_inventory = fake_get_cached_inventory  # type: ignore
    try:
        resp = await async_client.get('/api/hosts/2/inventory?type=stack_member')
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert 'items' in data
        assert len(data['items']) == 2
        assert all(it.get('type') == 'stack_member' for it in data['items'])
    finally:
        integrations_api._get_cached_inventory = orig  # restore
