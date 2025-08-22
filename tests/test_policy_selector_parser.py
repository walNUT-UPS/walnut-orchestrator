"""
Unit tests for policy selector parsing and validation.

Tests VM selectors (104,204,311-318), port selectors (1/1-1/4,1/A1-1/B4),
invalid grammar handling, and canonical ID matching.
"""
import pytest
from unittest.mock import Mock, patch
from walnut.policy.compile import PolicyCompiler
from walnut.policy.models import PolicySpec, ValidationResult


class TestVMSelectorParser:
    """Test VM selector parsing with various input formats."""
    
    def test_single_vm_selector(self):
        """Test parsing single VM ID."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.validate_and_compile(spec)
        
        assert result.ok
        assert len(result.schema) == 0
        assert len(result.compile) == 0
        assert result.ir is not None
        assert len(result.ir.action_group.actions) == 1
        action = result.ir.action_group.actions[0]
        assert "104" in action.selector.external_ids
    
    def test_comma_separated_vms(self):
        """Test parsing comma-separated VM list."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104,204,305"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.validate_and_compile(spec)
        
        assert result.ok
        action = result.ir.action_group.actions[0]
        expected_ids = ["104", "204", "305"]
        for vm_id in expected_ids:
            assert vm_id in action.selector.external_ids
    
    def test_vm_range_expansion(self):
        """Test VM range expansion (311-318)."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": ["311-318"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.validate_and_compile(spec)
        
        assert result.ok
        action = result.ir.action_group.actions[0]
        expected_ids = ["311", "312", "313", "314", "315", "316", "317", "318"]
        for vm_id in expected_ids:
            assert vm_id in action.selector.external_ids
    
    def test_mixed_csv_and_range(self):
        """Test mixed comma-separated and range VM selectors."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle", 
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104,204,311-318"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.validate_and_compile(spec)
        
        assert result.ok
        action = result.ir.action_group.actions[0]
        expected_ids = ["104", "204", "311", "312", "313", "314", "315", "316", "317", "318"]
        for vm_id in expected_ids:
            assert vm_id in action.selector.external_ids


class TestPortSelectorParser:
    """Test port selector parsing with alpha-numeric slots."""
    
    def test_simple_port_range(self):
        """Test simple numeric port range (1/1-1/4)."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "poe.control",
                    "verb": "disable",
                    "selector": {"external_ids": ["1/1-1/4"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.validate_and_compile(spec)
        
        assert result.ok
        action = result.ir.action_group.actions[0]
        expected_ports = ["1/1", "1/2", "1/3", "1/4"]
        for port_id in expected_ports:
            assert port_id in action.selector.external_ids
    
    def test_alpha_port_range(self):
        """Test alpha port range (1/A1-1/B4)."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "poe.control",
                    "verb": "disable", 
                    "selector": {"external_ids": ["1/A1-1/B4"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.validate_and_compile(spec)
        
        assert result.ok
        action = result.ir.action_group.actions[0]
        # This would expand A1,A2,A3,A4,B1,B2,B3,B4
        expected_ports = ["1/A1", "1/A2", "1/A3", "1/A4", "1/B1", "1/B2", "1/B3", "1/B4"]
        for port_id in expected_ports:
            assert port_id in action.selector.external_ids
    
    def test_mixed_port_formats(self):
        """Test mixed port selector formats."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "poe.control",
                    "verb": "disable",
                    "selector": {"external_ids": ["1/1-1/4,1/A1-1/B4"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.validate_and_compile(spec)
        
        assert result.ok
        action = result.ir.action_group.actions[0]
        expected_ports = [
            "1/1", "1/2", "1/3", "1/4",
            "1/A1", "1/A2", "1/A3", "1/A4", 
            "1/B1", "1/B2", "1/B3", "1/B4"
        ]
        for port_id in expected_ports:
            assert port_id in action.selector.external_ids


class TestSelectorValidation:
    """Test selector validation and error handling."""
    
    def test_invalid_selector_grammar(self):
        """Test that invalid selector grammar raises compile blocker with JSON pointer."""
        spec = {
            "name": "Test Policy",
            "version": "1.0", 
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": ["invalid-range-format-"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.validate_and_compile(spec)
        
        assert not result.ok
        assert len(result.compile) > 0
        
        # Check for blocker with JSON pointer
        blocker_found = False
        for error in result.compile:
            if error.severity == "blocker" and "/action_group/actions/0/selector/external_ids" in error.path:
                blocker_found = True
                break
        assert blocker_found
    
    def test_empty_selector_warning(self):
        """Test that empty selector generates warning."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": []}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.validate_and_compile(spec)
        
        # Should compile but with warnings
        warning_found = False
        for error in result.compile:
            if error.severity == "warn" and "empty selection" in error.message.lower():
                warning_found = True
                break
        assert warning_found
    
    def test_canonical_id_matching(self):
        """Test that selectors match canonical IDs from discovery."""
        spec = {
            "name": "Test Policy", 
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        # Mock inventory to return canonical IDs
        with patch('walnut.inventory.create_inventory_index') as mock_create:
            mock_inventory = Mock()
            mock_inventory.resolve_canonical_ids.return_value = ["vm-104"]
            mock_create.return_value = mock_inventory
            
            compiler = PolicyCompiler()
            result = compiler.compile(spec)
            
            assert result.ok
            # Canonical ID should be resolved during compilation
            action = result.ir.action_group.actions[0]
            assert "104" in action.selector.external_ids  # Original ID preserved