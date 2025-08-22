"""
Integration tests for driver preflight depth.

Tests Proxmox and AOS-S driver dry-run cases including VM states,
permission errors, POE support checks, and CLI plan previews.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from walnut.policy.engine import PolicyEngine
from walnut.policy.models import PolicyIR, Severity


class TestProxmoxDriverPreflight:
    """Test Proxmox driver dry-run preflight checks."""
    
    @pytest.mark.asyncio
    async def test_vm_running_to_stopped_preflight(self):
        """Test dry-run for VM shutdown when VM is running."""
        # Mock policy IR for VM shutdown
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="vm.lifecycle",
                verb="shutdown",
                selector=Mock(external_ids=["104"]),
                options={"timeout": 300}
            )
        ]
        
        # Mock Proxmox integration
        with patch('walnut.integrations.proxmox.ProxmoxIntegration') as MockProxmox:
            mock_integration = Mock()
            
            # Mock VM current state as running
            mock_integration.get_vm_status.return_value = {
                "vmid": "104",
                "status": "running",
                "name": "test-vm-104",
                "node": "pve1"
            }
            
            # Mock dry-run result
            mock_integration.dry_run_action.return_value = {
                "action": "shutdown",
                "target": {"id": "104", "name": "test-vm-104"},
                "current_state": "running",
                "effects": {"from": "running", "to": "stopped"},
                "severity": "info",
                "estimated_duration": 30,
                "notes": "VM will be gracefully shut down"
            }
            
            MockProxmox.return_value = mock_integration
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir)
            
            assert result.severity == Severity.INFO
            assert len(result.plan) == 1
            
            step = result.plan[0] 
            assert step["action"] == "shutdown"
            assert step["effects"]["from"] == "running"
            assert step["effects"]["to"] == "stopped"
            assert step["severity"] == "info"
    
    @pytest.mark.asyncio
    async def test_vm_already_stopped_preflight(self):
        """Test dry-run for VM shutdown when VM is already stopped."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="vm.lifecycle",
                verb="shutdown",
                selector=Mock(external_ids=["204"]),
                options={}
            )
        ]
        
        with patch('walnut.integrations.proxmox.ProxmoxIntegration') as MockProxmox:
            mock_integration = Mock()
            
            # Mock VM current state as already stopped
            mock_integration.get_vm_status.return_value = {
                "vmid": "204", 
                "status": "stopped",
                "name": "test-vm-204",
                "node": "pve2"
            }
            
            # Mock dry-run result for no-op
            mock_integration.dry_run_action.return_value = {
                "action": "shutdown",
                "target": {"id": "204", "name": "test-vm-204"},
                "current_state": "stopped",
                "effects": {"from": "stopped", "to": "stopped"},
                "severity": "info",
                "estimated_duration": 0,
                "notes": "VM is already stopped - no action needed"
            }
            
            MockProxmox.return_value = mock_integration
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir)
            
            assert result.severity == Severity.INFO
            assert len(result.plan) == 1
            
            step = result.plan[0]
            assert step["action"] == "shutdown"
            assert step["effects"]["from"] == "stopped"
            assert step["effects"]["to"] == "stopped"
            assert "already stopped" in step["notes"]
    
    @pytest.mark.asyncio
    async def test_vm_permission_error_preflight(self):
        """Test dry-run when user lacks permissions for VM operation."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="vm.lifecycle",
                verb="shutdown",
                selector=Mock(external_ids=["305"]),
                options={}
            )
        ]
        
        with patch('walnut.integrations.proxmox.ProxmoxIntegration') as MockProxmox:
            mock_integration = Mock()
            
            # Mock permission error
            mock_integration.get_vm_status.side_effect = PermissionError("Access denied for VM 305")
            
            # Mock dry-run result with permission error
            mock_integration.dry_run_action.return_value = {
                "action": "shutdown",
                "target": {"id": "305", "name": "unknown"},
                "current_state": "unknown",
                "effects": None,
                "severity": "error",
                "estimated_duration": None,
                "notes": "Permission denied - insufficient privileges for VM operations",
                "error": "Access denied for VM 305"
            }
            
            MockProxmox.return_value = mock_integration
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir)
            
            assert result.severity == Severity.ERROR
            assert len(result.plan) == 1
            
            step = result.plan[0]
            assert step["severity"] == "error"
            assert "permission denied" in step["notes"].lower()
            assert step["effects"] is None
    
    @pytest.mark.asyncio
    async def test_vm_start_preflight(self):
        """Test dry-run for VM start operation."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="vm.lifecycle",
                verb="start",
                selector=Mock(external_ids=["106"]),
                options={"wait_for_boot": True}
            )
        ]
        
        with patch('walnut.integrations.proxmox.ProxmoxIntegration') as MockProxmox:
            mock_integration = Mock()
            
            mock_integration.get_vm_status.return_value = {
                "vmid": "106",
                "status": "stopped", 
                "name": "test-vm-106",
                "node": "pve1"
            }
            
            mock_integration.dry_run_action.return_value = {
                "action": "start",
                "target": {"id": "106", "name": "test-vm-106"},
                "current_state": "stopped",
                "effects": {"from": "stopped", "to": "running"},
                "severity": "info",
                "estimated_duration": 60,
                "notes": "VM will be started and boot process monitored"
            }
            
            MockProxmox.return_value = mock_integration
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir)
            
            assert result.severity == Severity.INFO
            step = result.plan[0]
            assert step["action"] == "start"
            assert step["effects"]["to"] == "running"


class TestAOSSDriverPreflight:
    """Test AOS-S driver dry-run preflight checks."""
    
    @pytest.mark.asyncio
    async def test_poe_supported_ports_check(self):
        """Test dry-run checks for POE supported ports."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="poe.control",
                verb="disable",
                selector=Mock(external_ids=["1/1", "1/2", "1/3"]),
                options={}
            )
        ]
        
        with patch('walnut.integrations.aos_s.AOSSIntegration') as MockAOSS:
            mock_integration = Mock()
            
            # Mock POE capability check
            mock_integration.get_poe_port_info.side_effect = [
                {
                    "port": "1/1",
                    "poe_supported": True,
                    "poe_enabled": True,
                    "power_consumption": 15.2,
                    "power_limit": 30.0
                },
                {
                    "port": "1/2", 
                    "poe_supported": True,
                    "poe_enabled": False,
                    "power_consumption": 0.0,
                    "power_limit": 30.0
                },
                {
                    "port": "1/3",
                    "poe_supported": False,  # Not POE capable
                    "poe_enabled": False,
                    "power_consumption": 0.0,
                    "power_limit": 0.0
                }
            ]
            
            mock_integration.dry_run_action.return_value = {
                "action": "poe_disable",
                "targets": [
                    {
                        "id": "1/1",
                        "current_state": "enabled",
                        "effects": {"from": "enabled", "to": "disabled"},
                        "severity": "info"
                    },
                    {
                        "id": "1/2", 
                        "current_state": "disabled",
                        "effects": {"from": "disabled", "to": "disabled"},
                        "severity": "info",
                        "notes": "POE already disabled"
                    },
                    {
                        "id": "1/3",
                        "current_state": "unsupported",
                        "effects": None,
                        "severity": "warn", 
                        "notes": "Port does not support POE"
                    }
                ],
                "severity": "warn"  # Due to unsupported port
            }
            
            MockAOSS.return_value = mock_integration
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir)
            
            assert result.severity == Severity.WARN  # Due to unsupported port
            assert len(result.plan) == 1
            
            step = result.plan[0]
            assert len(step["targets"]) == 3
            
            # Check individual port results
            port_1_1 = next(t for t in step["targets"] if t["id"] == "1/1")
            assert port_1_1["effects"]["to"] == "disabled"
            
            port_1_3 = next(t for t in step["targets"] if t["id"] == "1/3")
            assert port_1_3["severity"] == "warn"
            assert "does not support POE" in port_1_3["notes"]
    
    @pytest.mark.asyncio  
    async def test_poe_protected_ports_check(self):
        """Test dry-run checks for protected ports list."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="poe.control",
                verb="disable",
                selector=Mock(external_ids=["1/1", "1/48"]),  # 1/48 might be uplink
                options={}
            )
        ]
        
        with patch('walnut.integrations.aos_s.AOSSIntegration') as MockAOSS:
            mock_integration = Mock()
            
            # Mock protected ports configuration
            mock_integration.get_protected_ports.return_value = ["1/48"]  # Uplink port protected
            
            mock_integration.dry_run_action.return_value = {
                "action": "poe_disable",
                "targets": [
                    {
                        "id": "1/1",
                        "current_state": "enabled",
                        "effects": {"from": "enabled", "to": "disabled"},
                        "severity": "info"
                    },
                    {
                        "id": "1/48",
                        "current_state": "enabled", 
                        "effects": None,
                        "severity": "error",
                        "notes": "Port is protected from POE operations (uplink port)"
                    }
                ],
                "severity": "error"  # Due to protected port
            }
            
            MockAOSS.return_value = mock_integration
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir)
            
            assert result.severity == Severity.ERROR
            step = result.plan[0]
            
            protected_port = next(t for t in step["targets"] if t["id"] == "1/48")
            assert protected_port["severity"] == "error"
            assert "protected" in protected_port["notes"]
    
    @pytest.mark.asyncio
    async def test_aos_s_cli_plan_preview(self):
        """Test AOS-S CLI plan preview generation."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="aos.port_admin",
                verb="down",
                selector=Mock(external_ids=["1/1/1", "1/1/2"]),
                options={}
            )
        ]
        
        with patch('walnut.integrations.aos_s.AOSSIntegration') as MockAOSS:
            mock_integration = Mock()
            
            # Mock CLI command preview
            mock_integration.generate_cli_preview.return_value = {
                "commands": [
                    "interface 1/1/1",
                    "   shutdown",
                    "interface 1/1/2", 
                    "   shutdown",
                    "write memory"
                ],
                "estimated_duration": 15,
                "reversible": True,
                "reverse_commands": [
                    "interface 1/1/1",
                    "   no shutdown",
                    "interface 1/1/2",
                    "   no shutdown", 
                    "write memory"
                ]
            }
            
            mock_integration.dry_run_action.return_value = {
                "action": "port_admin_down",
                "targets": [
                    {"id": "1/1/1", "current_state": "up", "effects": {"from": "up", "to": "down"}},
                    {"id": "1/1/2", "current_state": "up", "effects": {"from": "up", "to": "down"}}
                ],
                "cli_preview": {
                    "commands": [
                        "interface 1/1/1", "   shutdown",
                        "interface 1/1/2", "   shutdown", 
                        "write memory"
                    ],
                    "estimated_duration": 15,
                    "reversible": True
                },
                "severity": "info"
            }
            
            MockAOSS.return_value = mock_integration
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir)
            
            assert result.severity == Severity.INFO
            step = result.plan[0]
            
            assert "cli_preview" in step
            assert len(step["cli_preview"]["commands"]) == 5
            assert "shutdown" in " ".join(step["cli_preview"]["commands"])
            assert step["cli_preview"]["reversible"] is True


class TestDriverPreflightEdgeCases:
    """Test driver preflight edge cases and error conditions."""
    
    @pytest.mark.asyncio
    async def test_integration_unavailable(self):
        """Test dry-run when integration/driver is unavailable."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="vm.lifecycle",
                verb="shutdown",
                selector=Mock(external_ids=["404"]),
                options={}
            )
        ]
        
        with patch('walnut.integrations.proxmox.ProxmoxIntegration') as MockProxmox:
            # Mock integration connection failure
            MockProxmox.side_effect = ConnectionError("Proxmox server unreachable")
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir)
            
            assert result.severity == Severity.ERROR
            assert len(result.plan) == 1
            
            step = result.plan[0]
            assert step["severity"] == "error"
            assert "unreachable" in step["notes"].lower() or "connection" in step["notes"].lower()
    
    @pytest.mark.asyncio
    async def test_mixed_driver_results(self):
        """Test dry-run with mixed success/error results across drivers."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="vm.lifecycle",
                verb="shutdown",
                selector=Mock(external_ids=["104"]),
                options={}
            ),
            Mock(
                capability="poe.control",
                verb="disable",
                selector=Mock(external_ids=["1/1"]),
                options={}
            )
        ]
        
        with patch('walnut.integrations.proxmox.ProxmoxIntegration') as MockProxmox:
            with patch('walnut.integrations.aos_s.AOSSIntegration') as MockAOSS:
                # Mock successful Proxmox operation
                mock_proxmox = Mock()
                mock_proxmox.dry_run_action.return_value = {
                    "action": "shutdown",
                    "target": {"id": "104", "name": "test-vm"},
                    "effects": {"from": "running", "to": "stopped"},
                    "severity": "info"
                }
                MockProxmox.return_value = mock_proxmox
                
                # Mock failed AOS-S operation
                mock_aos_s = Mock()
                mock_aos_s.dry_run_action.return_value = {
                    "action": "poe_disable",
                    "targets": [{
                        "id": "1/1",
                        "effects": None,
                        "severity": "error",
                        "notes": "Authentication failed"
                    }],
                    "severity": "error"
                }
                MockAOSS.return_value = mock_aos_s
                
                engine = PolicyEngine()
                result = await engine.dry_run_policy(policy_ir)
                
                # Overall severity should escalate to error due to AOS-S failure
                assert result.severity == Severity.ERROR
                assert len(result.plan) == 2
                
                # Verify individual step results
                vm_step = result.plan[0]
                poe_step = result.plan[1]
                
                assert vm_step["severity"] == "info"
                assert poe_step["severity"] == "error"
    
    @pytest.mark.asyncio
    async def test_inventory_refresh_sla_honored(self):
        """Test that inventory refresh SLA is honored during dry-run."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="vm.lifecycle",
                verb="shutdown", 
                selector=Mock(labels={"tier": "dev"}),  # Dynamic selector requires fresh inventory
                options={}
            )
        ]
        
        with patch('walnut.inventory.create_inventory_index') as mock_inventory:
            mock_index = Mock()
            
            # Mock fresh inventory (within SLA)
            mock_index.is_stale.return_value = False
            mock_index.last_refresh_time = 1640995200  # Recent timestamp
            mock_index.refresh_sla_seconds = 300  # 5 minutes
            
            mock_index.resolve_targets.return_value = [
                {"id": "vm-104", "name": "dev-vm-1", "labels": {"tier": "dev"}},
                {"id": "vm-105", "name": "dev-vm-2", "labels": {"tier": "dev"}}
            ]
            
            mock_inventory.return_value = mock_index
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir, refresh_inventory=True)
            
            # Should not have stale inventory warnings
            stale_warnings = [
                step for step in result.plan 
                if step.get("severity") == "warn" and "stale" in step.get("notes", "").lower()
            ]
            assert len(stale_warnings) == 0
    
    @pytest.mark.asyncio
    async def test_stale_inventory_warning(self):
        """Test stale inventory generates warning during dry-run."""
        policy_ir = Mock()
        policy_ir.action_group = Mock()
        policy_ir.action_group.actions = [
            Mock(
                capability="vm.lifecycle",
                verb="shutdown",
                selector=Mock(labels={"environment": "staging"}),
                options={}
            )
        ]
        
        with patch('walnut.inventory.create_inventory_index') as mock_inventory:
            mock_index = Mock()
            
            # Mock stale inventory (outside SLA)
            mock_index.is_stale.return_value = True
            mock_index.last_refresh_time = 1640995200 - 900  # 15 minutes ago
            mock_index.refresh_sla_seconds = 300  # 5 minute SLA
            
            mock_index.resolve_targets.return_value = []  # Empty due to staleness
            
            mock_inventory.return_value = mock_index
            
            engine = PolicyEngine()
            result = await engine.dry_run_policy(policy_ir, refresh_inventory=False)
            
            assert result.severity == Severity.WARN
            
            # Should have stale inventory warning
            stale_warnings = [
                msg for msg in result.warnings
                if "stale inventory" in msg.lower()
            ]
            assert len(stale_warnings) > 0