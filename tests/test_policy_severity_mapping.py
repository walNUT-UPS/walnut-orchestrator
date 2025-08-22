"""
Unit tests for policy severity mapping and edge cases.

Tests info/warn/error/blocker transitions according to policy.md,
including edge cases like empty selection, stale inventory, and host unreachable.
"""
import pytest
from unittest.mock import Mock, patch
from walnut.policy.compile import PolicyCompiler
from walnut.policy.models import Severity, ValidationError


class TestSeverityMapping:
    """Test severity level assignments and transitions."""
    
    def test_info_severity_normal_policy(self):
        """Test info severity for normal, valid policies."""
        spec = {
            "name": "Normal Policy",
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
        result = compiler.compile(spec)
        
        assert result.ok
        assert result.severity == Severity.INFO
        
        # Should have no warnings or errors
        warnings = [err for err in result.compile if err.severity == "warn"]
        errors = [err for err in result.compile if err.severity == "error"]
        blockers = [err for err in result.compile if err.severity == "blocker"]
        
        assert len(warnings) == 0
        assert len(errors) == 0
        assert len(blockers) == 0
    
    def test_warn_severity_empty_selection(self):
        """Test warn severity for empty selection."""
        spec = {
            "name": "Empty Selection Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": []}  # Empty selection
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        # Policy should compile but with warnings
        assert result.severity == Severity.WARN
        
        warnings = [err for err in result.compile if err.severity == "warn"]
        assert len(warnings) > 0
        
        # Check for empty selection warning
        empty_selection_warning = False
        for warning in warnings:
            if "empty selection" in warning.message.lower():
                empty_selection_warning = True
                break
        assert empty_selection_warning
    
    def test_warn_severity_stale_inventory(self):
        """Test warn severity for stale inventory."""
        spec = {
            "name": "Stale Inventory Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"labels": {"tier": "dev"}}
                }]
            }
        }
        
        # Mock stale inventory condition
        with patch('walnut.inventory.create_inventory_index') as mock_create:
            mock_inventory = Mock()
            mock_inventory.is_stale.return_value = True  # Simulate stale inventory
            mock_create.return_value = mock_inventory
            
            compiler = PolicyCompiler()
            result = compiler.compile(spec)
            
            assert result.severity == Severity.WARN
            
            warnings = [err for err in result.compile if err.severity == "warn"]
            assert len(warnings) > 0
            
            # Check for stale inventory warning
            stale_inventory_warning = False
            for warning in warnings:
                if "stale inventory" in warning.message.lower():
                    stale_inventory_warning = True
                    break
            assert stale_inventory_warning
    
    def test_error_severity_host_unreachable(self):
        """Test error severity for unreachable hosts."""
        spec = {
            "name": "Unreachable Host Policy",
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
        
        # Mock unreachable host condition
        with patch('walnut.inventory.create_inventory_index') as mock_create:
            mock_inventory = Mock()
            mock_inventory.check_host_reachability.return_value = False  # Host unreachable
            mock_create.return_value = mock_inventory
            
            compiler = PolicyCompiler()
            result = compiler.compile(spec)
            
            assert result.severity == Severity.ERROR
            
            errors = [err for err in result.compile if err.severity == "error"]
            assert len(errors) > 0
            
            # Check for host unreachable error
            host_unreachable_error = False
            for error in errors:
                if "unreachable" in error.message.lower():
                    host_unreachable_error = True
                    break
            assert host_unreachable_error
    
    def test_blocker_severity_unknown_capability(self):
        """Test blocker severity for unknown capabilities."""
        spec = {
            "name": "Unknown Capability Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "nonexistent.capability",  # Unknown capability
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        assert not result.ok
        assert result.severity == Severity.BLOCKER
        
        blockers = [err for err in result.compile if err.severity == "blocker"]
        assert len(blockers) > 0
        
        # Check for capability blocker
        capability_blocker = False
        for blocker in blockers:
            if ("capability" in blocker.message.lower() and 
                "nonexistent.capability" in blocker.message):
                capability_blocker = True
                break
        assert capability_blocker


class TestSeverityTransitions:
    """Test severity level transitions and edge cases."""
    
    def test_severity_escalation_multiple_issues(self):
        """Test that severity escalates with multiple issues."""
        spec = {
            "name": "Multiple Issues Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [
                    {
                        "capability": "vm.lifecycle",
                        "verb": "shutdown",
                        "selector": {"external_ids": []}  # Empty selection (warn)
                    },
                    {
                        "capability": "nonexistent.capability",  # Unknown capability (blocker)
                        "verb": "shutdown", 
                        "selector": {"external_ids": ["104"]}
                    }
                ]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        # Should be blocker due to unknown capability, despite other warnings
        assert not result.ok
        assert result.severity == Severity.BLOCKER
        
        warnings = [err for err in result.compile if err.severity == "warn"]
        blockers = [err for err in result.compile if err.severity == "blocker"]
        
        assert len(warnings) > 0  # Empty selection warning
        assert len(blockers) > 0  # Unknown capability blocker
    
    def test_severity_downgrade_after_fix(self):
        """Test severity changes when issues are fixed."""
        # First, policy with blocker
        spec_with_blocker = {
            "name": "Policy with Blocker",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "nonexistent.capability",  # Unknown capability (blocker)
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result_blocker = compiler.compile(spec_with_blocker)
        
        assert not result_blocker.ok
        assert result_blocker.severity == Severity.BLOCKER
        
        # Fixed version - replace with known capability
        spec_fixed = {
            "name": "Policy with Blocker",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",  # Known capability
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        result_fixed = compiler.compile(spec_fixed)
        
        assert result_fixed.ok
        assert result_fixed.severity == Severity.INFO  # Should downgrade to info
    
    def test_warn_to_error_progression(self):
        """Test progression from warn to error with inventory issues."""
        spec = {
            "name": "Progressive Severity Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"labels": {"tier": "dev"}}
                }]
            }
        }
        
        # First compilation - just stale inventory (warn)
        with patch('walnut.inventory.create_inventory_index') as mock_create:
            mock_inventory = Mock()
            mock_inventory.is_stale.return_value = True  # Stale but accessible
            mock_inventory.check_host_reachability.return_value = True
            mock_create.return_value = mock_inventory
            
            compiler = PolicyCompiler()
            result_warn = compiler.compile(spec)
            
            assert result_warn.severity == Severity.WARN
        
        # Second compilation - host becomes unreachable (error)
        with patch('walnut.inventory.create_inventory_index') as mock_create:
            mock_inventory = Mock()
            mock_inventory.is_stale.return_value = True  # Still stale
            mock_inventory.check_host_reachability.return_value = False  # Now unreachable
            mock_create.return_value = mock_inventory
            
            result_error = compiler.compile(spec)
            
            assert result_error.severity == Severity.ERROR


class TestEdgeCases:
    """Test edge cases in severity mapping."""
    
    def test_no_actions_policy(self):
        """Test policy with no actions."""
        spec = {
            "name": "No Actions Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {"actions": []}  # No actions
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        assert not result.ok
        assert result.severity == Severity.BLOCKER
        
        blockers = [err for err in result.compile if err.severity == "blocker"]
        assert len(blockers) > 0
        
        # Should have blocker for no actions
        no_actions_blocker = False
        for blocker in blockers:
            if "no actions" in blocker.message.lower():
                no_actions_blocker = True
                break
        assert no_actions_blocker
    
    def test_complex_selector_combinations(self):
        """Test complex selector combinations and their severity impact."""
        spec = {
            "name": "Complex Selectors Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {
                        "external_ids": ["104", "204"],
                        "labels": {"tier": "dev", "environment": "staging"},
                        "attrs": {"cpu_count": {"gte": 2}, "memory_gb": {"lt": 8}}
                    }
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        assert result.ok
        # Complex selectors should still be info if everything resolves correctly
        assert result.severity == Severity.INFO
        
        # Should flag as requiring dynamic resolution
        assert result.ir.dynamic_resolution is True