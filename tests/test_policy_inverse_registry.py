"""
Unit tests for policy inverse registry functionality.

Tests Proxmox start↔shutdown, AOS-S admin up/down, POE on/off inverse mappings,
and identification of non-invertible actions.
"""
import pytest
from unittest.mock import Mock, patch
from walnut.policy.compile import PolicyCompiler
from walnut.policy.models import PolicySpec


class TestCapabilityInverseRegistry:
    """Test capability/verb inverse mappings."""
    
    def test_vm_lifecycle_inverse_mapping(self):
        """Test VM lifecycle action inversions (shutdown ↔ start)."""
        # Test shutdown → start inverse
        shutdown_spec = {
            "name": "Shutdown Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104", "204"]}
                }]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "vm.lifecycle": {
                    "shutdown": "start",
                    "start": "shutdown",
                    "restart": None  # Non-invertible
                }
            }
            
            compiler = PolicyCompiler()
            inverse_spec = compiler.create_inverse_spec(shutdown_spec)
            
            assert inverse_spec["name"].startswith("Inverse of")
            assert inverse_spec["action_group"]["actions"][0]["verb"] == "start"
            assert inverse_spec["action_group"]["actions"][0]["capability"] == "vm.lifecycle"
            # Selector should be preserved
            assert inverse_spec["action_group"]["actions"][0]["selector"]["external_ids"] == ["104", "204"]
        
        # Test start → shutdown inverse
        start_spec = {
            "name": "Start Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 2 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "start",
                    "selector": {"external_ids": ["104", "204"]}
                }]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "vm.lifecycle": {
                    "shutdown": "start",
                    "start": "shutdown",
                    "restart": None
                }
            }
            
            inverse_spec = compiler.create_inverse_spec(start_spec)
            
            assert inverse_spec["action_group"]["actions"][0]["verb"] == "shutdown"
    
    def test_poe_control_inverse_mapping(self):
        """Test POE control action inversions (enable ↔ disable)."""
        # Test disable → enable inverse
        disable_spec = {
            "name": "POE Disable Policy",
            "version": "1.0", 
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "poe.control",
                    "verb": "disable",
                    "selector": {"external_ids": ["1/1", "1/2", "1/3"]}
                }]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "poe.control": {
                    "enable": "disable",
                    "disable": "enable"
                }
            }
            
            compiler = PolicyCompiler()
            inverse_spec = compiler.create_inverse_spec(disable_spec)
            
            assert inverse_spec["action_group"]["actions"][0]["verb"] == "enable"
            assert inverse_spec["action_group"]["actions"][0]["capability"] == "poe.control"
            assert inverse_spec["action_group"]["actions"][0]["selector"]["external_ids"] == ["1/1", "1/2", "1/3"]
        
        # Test enable → disable inverse
        enable_spec = {
            "name": "POE Enable Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 2 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "poe.control",
                    "verb": "enable",
                    "selector": {"external_ids": ["1/A1", "1/B2"]}
                }]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "poe.control": {
                    "enable": "disable",
                    "disable": "enable"
                }
            }
            
            inverse_spec = compiler.create_inverse_spec(enable_spec)
            
            assert inverse_spec["action_group"]["actions"][0]["verb"] == "disable"
    
    def test_aos_s_admin_inverse_mapping(self):
        """Test AOS-S admin port inversions (up ↔ down)."""
        # Test admin down → admin up inverse
        admin_down_spec = {
            "name": "AOS-S Admin Down Policy", 
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "aos.port_admin",
                    "verb": "down",
                    "selector": {"external_ids": ["1/1/1", "1/1/2"]}
                }]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "aos.port_admin": {
                    "up": "down",
                    "down": "up"
                }
            }
            
            compiler = PolicyCompiler()
            inverse_spec = compiler.create_inverse_spec(admin_down_spec)
            
            assert inverse_spec["action_group"]["actions"][0]["verb"] == "up"
            assert inverse_spec["action_group"]["actions"][0]["capability"] == "aos.port_admin"
        
        # Test admin up → admin down inverse
        admin_up_spec = {
            "name": "AOS-S Admin Up Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 2 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "aos.port_admin",
                    "verb": "up",
                    "selector": {"external_ids": ["1/1/1", "1/1/2"]}
                }]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "aos.port_admin": {
                    "up": "down", 
                    "down": "up"
                }
            }
            
            inverse_spec = compiler.create_inverse_spec(admin_up_spec)
            
            assert inverse_spec["action_group"]["actions"][0]["verb"] == "down"


class TestNonInvertibleActions:
    """Test identification and handling of non-invertible actions."""
    
    def test_non_invertible_action_flagged(self):
        """Test that non-invertible actions are correctly flagged."""
        restart_spec = {
            "name": "VM Restart Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle", 
                    "verb": "restart",  # Non-invertible action
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "vm.lifecycle": {
                    "shutdown": "start",
                    "start": "shutdown",
                    "restart": None  # Explicitly marked as non-invertible
                }
            }
            
            compiler = PolicyCompiler()
            
            # Should raise exception or return error when trying to invert
            with pytest.raises(ValueError, match="non-invertible"):
                compiler.create_inverse_spec(restart_spec)
    
    def test_list_non_invertible_actions(self):
        """Test listing all non-invertible actions from registry."""
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "vm.lifecycle": {
                    "shutdown": "start",
                    "start": "shutdown", 
                    "restart": None,    # Non-invertible
                    "reset": None       # Non-invertible
                },
                "poe.control": {
                    "enable": "disable",
                    "disable": "enable"
                },
                "system.maintenance": {
                    "backup": None,     # Non-invertible
                    "cleanup": None     # Non-invertible  
                }
            }
            
            compiler = PolicyCompiler()
            non_invertible = compiler.list_non_invertible_actions()
            
            expected = [
                "vm.lifecycle.restart",
                "vm.lifecycle.reset", 
                "system.maintenance.backup",
                "system.maintenance.cleanup"
            ]
            
            for action in expected:
                assert action in non_invertible
    
    def test_mixed_invertible_non_invertible_policy(self):
        """Test policy with mix of invertible and non-invertible actions."""
        mixed_spec = {
            "name": "Mixed Actions Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [
                    {
                        "capability": "vm.lifecycle",
                        "verb": "shutdown",  # Invertible
                        "selector": {"external_ids": ["104"]}
                    },
                    {
                        "capability": "vm.lifecycle", 
                        "verb": "restart",   # Non-invertible
                        "selector": {"external_ids": ["204"]}
                    },
                    {
                        "capability": "poe.control",
                        "verb": "disable",   # Invertible
                        "selector": {"external_ids": ["1/1"]}
                    }
                ]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "vm.lifecycle": {
                    "shutdown": "start",
                    "start": "shutdown",
                    "restart": None  # Non-invertible
                },
                "poe.control": {
                    "enable": "disable",
                    "disable": "enable"
                }
            }
            
            compiler = PolicyCompiler()
            
            # Should raise exception due to non-invertible action in mix
            with pytest.raises(ValueError, match="contains non-invertible actions"):
                compiler.create_inverse_spec(mixed_spec)


class TestInverseSpecGeneration:
    """Test complete inverse spec generation."""
    
    def test_inverse_spec_metadata(self):
        """Test inverse spec metadata generation."""
        original_spec = {
            "name": "Original Policy",
            "version": "1.0",
            "priority": 100,
            "enabled": True,
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
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "vm.lifecycle": {
                    "shutdown": "start",
                    "start": "shutdown"
                }
            }
            
            compiler = PolicyCompiler()
            inverse_spec = compiler.create_inverse_spec(original_spec)
            
            # Name should be prefixed
            assert inverse_spec["name"] == "Inverse of Original Policy"
            
            # Should be disabled by default
            assert inverse_spec["enabled"] is False
            
            # Priority should be preserved or adjusted
            assert "priority" in inverse_spec
            
            # Version should be preserved
            assert inverse_spec["version"] == "1.0"
    
    def test_inverse_preserves_selectors(self):
        """Test that inverse spec preserves target selectors."""
        original_spec = {
            "name": "Complex Selector Policy",
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
                        "attrs": {"cpu_count": {"gte": 4}}
                    },
                    "options": {"timeout": 300, "force": False}
                }]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "vm.lifecycle": {
                    "shutdown": "start",
                    "start": "shutdown"
                }
            }
            
            compiler = PolicyCompiler()
            inverse_spec = compiler.create_inverse_spec(original_spec)
            
            inverse_action = inverse_spec["action_group"]["actions"][0]
            
            # Verb should be inverted
            assert inverse_action["verb"] == "start"
            
            # Selector should be preserved exactly
            assert inverse_action["selector"]["external_ids"] == ["104", "204"]
            assert inverse_action["selector"]["labels"]["tier"] == "dev"
            assert inverse_action["selector"]["labels"]["environment"] == "staging"
            assert inverse_action["selector"]["attrs"]["cpu_count"]["gte"] == 4
            
            # Options should be preserved
            assert inverse_action["options"]["timeout"] == 300
            assert inverse_action["options"]["force"] is False
    
    def test_inverse_needs_input_identification(self):
        """Test identification of fields requiring user input in inverse."""
        timer_spec = {
            "name": "Timer Policy",
            "version": "1.0",
            "trigger_group": {
                "triggers": [{
                    "type": "timer.cron",
                    "schedule": {"cron": "0 1 * * *"}  # This will need user input for inverse
                }]
            },
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        with patch('walnut.policy.compile.get_inverse_registry') as mock_registry:
            mock_registry.return_value = {
                "vm.lifecycle": {
                    "shutdown": "start",
                    "start": "shutdown"
                }
            }
            
            compiler = PolicyCompiler()
            inverse_result = compiler.create_inverse_spec_with_metadata(timer_spec)
            
            assert "needs_input" in inverse_result
            assert len(inverse_result["needs_input"]) > 0
            
            # Should identify timer schedule as needing input
            timer_input_needed = False
            for field_path in inverse_result["needs_input"]:
                if "trigger_group.triggers" in field_path and "schedule" in field_path:
                    timer_input_needed = True
                    break
            assert timer_input_needed