"""
Unit tests for policy compilation pipeline.

Tests valid spec to IR compilation, deterministic hashing,
unknown capability/verb handling, and dynamic vs static resolution.
"""
import pytest
import hashlib
from walnut.policy.compile import PolicyCompiler, compute_spec_hash, normalize_spec
from walnut.policy.models import PolicySpec, ValidationResult, Severity


class TestPolicyCompilation:
    """Test policy compilation from spec to IR."""
    
    def test_valid_spec_to_ir(self):
        """Test successful compilation of valid spec to IR."""
        spec = {
            "name": "Test Shutdown Policy",
            "version": "1.0",
            "trigger_group": {
                "triggers": [{
                    "type": "timer.cron",
                    "schedule": {"cron": "0 1 * * 0"}
                }]
            },
            "condition_group": {
                "conditions": []
            },
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {
                        "external_ids": ["104", "204"],
                        "labels": {"tier": "dev"}
                    },
                    "options": {"timeout": 300}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        assert result.ok
        assert result.ir is not None
        assert len(result.schema) == 0
        assert len(result.compile) == 0
        
        # Verify IR structure
        ir = result.ir
        assert ir.name == "Test Shutdown Policy"
        assert ir.version == "1.0"
        assert len(ir.trigger_group.triggers) == 1
        assert ir.trigger_group.triggers[0].type == "timer.cron"
        assert len(ir.action_group.actions) == 1
        
        action = ir.action_group.actions[0]
        assert action.capability == "vm.lifecycle"
        assert action.verb == "shutdown"
        assert "104" in action.selector.external_ids
        assert "204" in action.selector.external_ids
        assert action.selector.labels["tier"] == "dev"
        assert action.options["timeout"] == 300
    
    def test_deterministic_hash_generation(self):
        """Test that identical specs generate identical hashes."""
        spec1 = {
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
        
        spec2 = {
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
        
        hash1 = compute_spec_hash(spec1)
        hash2 = compute_spec_hash(spec2)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex string
    
    def test_hash_changes_with_content(self):
        """Test that hash changes when spec content changes."""
        spec1 = {
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
        
        spec2 = {
            "name": "Different Policy",  # Changed name
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
        
        hash1 = compute_spec_hash(spec1)
        hash2 = compute_spec_hash(spec2)
        
        assert hash1 != hash2
    
    def test_hash_ignores_key_order(self):
        """Test that hash is consistent regardless of key order."""
        spec1 = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            },
            "condition_group": {"conditions": []}
        }
        
        spec2 = {
            "version": "1.0",
            "name": "Test Policy",
            "condition_group": {"conditions": []},
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "action_group": {
                "actions": [{
                    "selector": {"external_ids": ["104"]},
                    "capability": "vm.lifecycle",
                    "verb": "shutdown"
                }]
            }
        }
        
        hash1 = compute_spec_hash(spec1)
        hash2 = compute_spec_hash(spec2)
        
        assert hash1 == hash2


class TestCapabilityValidation:
    """Test capability and verb validation."""
    
    def test_unknown_capability_blocker(self):
        """Test that unknown capability generates blocker error."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "unknown.capability",  # Invalid capability
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        assert not result.ok
        assert len(result.compile) > 0
        
        # Check for capability blocker
        blocker_found = False
        for error in result.compile:
            if (error.severity == "blocker" and 
                "unknown.capability" in error.message and
                "/action_group/actions/0/capability" in error.path):
                blocker_found = True
                break
        assert blocker_found
    
    def test_unknown_verb_blocker(self):
        """Test that unknown verb generates blocker error."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "unknown_verb",  # Invalid verb
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        assert not result.ok
        assert len(result.compile) > 0
        
        # Check for verb blocker
        blocker_found = False
        for error in result.compile:
            if (error.severity == "blocker" and 
                "unknown_verb" in error.message and
                "/action_group/actions/0/verb" in error.path):
                blocker_found = True
                break
        assert blocker_found
    
    def test_valid_capability_verb_combinations(self):
        """Test valid capability/verb combinations."""
        valid_specs = [
            {
                "capability": "vm.lifecycle",
                "verb": "shutdown"
            },
            {
                "capability": "vm.lifecycle", 
                "verb": "start"
            },
            {
                "capability": "poe.control",
                "verb": "disable"
            },
            {
                "capability": "poe.control",
                "verb": "enable"
            }
        ]
        
        for action_spec in valid_specs:
            spec = {
                "name": "Test Policy",
                "version": "1.0",
                "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
                "condition_group": {"conditions": []},
                "action_group": {
                    "actions": [{
                        "capability": action_spec["capability"],
                        "verb": action_spec["verb"],
                        "selector": {"external_ids": ["104"]}
                    }]
                }
            }
            
            compiler = PolicyCompiler()
            result = compiler.compile(spec)
            
            assert result.ok, f"Failed for {action_spec['capability']}.{action_spec['verb']}"


class TestResolutionFlags:
    """Test dynamic vs static resolution flagging."""
    
    def test_dynamic_resolution_flagged(self):
        """Test that dynamic resolution is correctly flagged."""
        spec = {
            "name": "Test Policy",
            "version": "1.0", 
            "dynamic_resolution": True,  # Explicit dynamic
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"labels": {"tier": "dev"}}  # Label-based = dynamic
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        assert result.ok
        assert result.ir.dynamic_resolution is True
    
    def test_static_resolution_flagged(self):
        """Test that static resolution is correctly flagged.""" 
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "dynamic_resolution": False,  # Explicit static
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle",
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104", "204"]}  # ID-based = static
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        assert result.ok
        assert result.ir.dynamic_resolution is False
    
    def test_auto_detect_dynamic_resolution(self):
        """Test automatic detection of dynamic resolution needs."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            # No explicit dynamic_resolution flag
            "trigger_group": {"triggers": [{"type": "timer.cron", "schedule": {"cron": "0 1 * * *"}}]},
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "vm.lifecycle", 
                    "verb": "shutdown",
                    "selector": {
                        "labels": {"environment": "staging"},  # Label-based requires dynamic
                        "attrs": {"cpu_count": {"gt": 4}}      # Attribute-based requires dynamic
                    }
                }]
            }
        }
        
        compiler = PolicyCompiler()
        result = compiler.compile(spec)
        
        assert result.ok
        # Should auto-detect dynamic resolution needed
        assert result.ir.dynamic_resolution is True


class TestNormalization:
    """Test spec normalization for consistent hashing."""
    
    def test_normalize_spec(self):
        """Test spec normalization removes noise and sorts keys."""
        spec = {
            "name": "Test Policy",
            "version": "1.0",
            "_comment": "This should be removed",  # Noise field
            "trigger_group": {
                "triggers": [{
                    "type": "timer.cron",
                    "schedule": {"cron": "0 1 * * *"}
                }]
            },
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "verb": "shutdown",          # Will be reordered
                    "capability": "vm.lifecycle", 
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        normalized = normalize_spec(spec)
        
        # Comment should be removed
        assert "_comment" not in str(normalized)
        
        # Keys should be in consistent order
        assert "capability" in normalized["action_group"]["actions"][0]
        assert "verb" in normalized["action_group"]["actions"][0]
        
        # Structure preserved
        assert normalized["name"] == "Test Policy"
        assert len(normalized["action_group"]["actions"]) == 1