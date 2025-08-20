"""
JSON Schema for validating plugin.yaml manifest files.

This schema defines the structure and validation rules for integration
type manifests used in the walNUT integrations architecture.
"""

from typing import Dict, Any

# JSON Schema for plugin.yaml validation
PLUGIN_MANIFEST_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://walnut.local/schemas/plugin-manifest.json",
    "title": "walNUT Plugin Manifest",
    "description": "Schema for validating plugin.yaml files for walNUT integrations",
    "type": "object",
    "required": ["id", "name", "version", "min_core_version", "category", "schema", "capabilities", "driver"],
    "additionalProperties": False,
    "properties": {
        "id": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9]*(?:\\.[a-z][a-z0-9]*)*$",
            "description": "Unique integration identifier in reverse domain format",
            "examples": ["walnut.proxmox.ve", "walnut.tapo.smartplug"]
        },
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "description": "Human-readable integration name",
            "examples": ["Proxmox VE", "TP-Link Tapo Smart Plug"]
        },
        "version": {
            "type": "string",
            "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-((?:0|[1-9]\\d*|\\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\\.(?:0|[1-9]\\d*|\\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\\+([0-9a-zA-Z-]+(?:\\.[0-9a-zA-Z-]+)*))?$",
            "description": "Semantic version of the integration",
            "examples": ["1.0.0", "1.2.3-beta.1", "2.0.0+build.123"]
        },
        "min_core_version": {
            "type": "string",
            "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-((?:0|[1-9]\\d*|\\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\\.(?:0|[1-9]\\d*|\\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\\+([0-9a-zA-Z-]+(?:\\.[0-9a-zA-Z-]+)*))?$",
            "description": "Minimum required walNUT core version",
            "examples": ["0.1.0", "1.0.0"]
        },
        "category": {
            "type": "string",
            "enum": [
                "host-orchestrator",
                "ups-management", 
                "power-control",
                "network-device",
                "smart-home",
                "monitoring",
                "notification",
                "storage",
                "compute"
            ],
            "description": "Integration category for organization and filtering"
        },
        "driver": {
            "type": "object",
            "required": ["entrypoint"],
            "additionalProperties": False,
            "properties": {
                "entrypoint": {
                    "type": "string",
                    "pattern": "^[a-zA-Z_][a-zA-Z0-9_]*:[a-zA-Z_][a-zA-Z0-9_]*$",
                    "description": "Python import path to driver class (module:ClassName)",
                    "examples": ["driver:ProxmoxVeDriver", "tapo_driver:TapoSmartPlugDriver"]
                },
                "language": {
                    "type": "string",
                    "enum": ["python"],
                    "default": "python",
                    "description": "Driver implementation language"
                },
                "runtime": {
                    "type": "string", 
                    "enum": ["embedded"],
                    "default": "embedded",
                    "description": "Runtime environment for the driver"
                }
            }
        },
        "schema": {
            "type": "object",
            "required": ["connection"],
            "additionalProperties": False,
            "properties": {
                "connection": {
                    "$ref": "https://json-schema.org/draft/2020-12/schema",
                    "description": "JSON Schema defining configuration fields for creating instances",
                    "examples": [
                        {
                            "type": "object",
                            "required": ["host", "api_token"],
                            "properties": {
                                "host": {"type": "string", "title": "Host"},
                                "port": {"type": "integer", "default": 8006},
                                "api_token": {"type": "string", "secret": True, "title": "API Token"}
                            }
                        }
                    ]
                }
            }
        },
        "capabilities": {
            "type": "array",
            "minItems": 1,
            "description": "List of capabilities provided by this integration",
            "items": {
                "type": "object",
                "required": ["id", "verbs", "targets"],
                "additionalProperties": False,
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^[a-z][a-z0-9_]*(?:\\.[a-z][a-z0-9_]*)*$",
                        "description": "Capability identifier (maps to driver method name)",
                        "examples": ["vm.lifecycle", "power.control", "inventory.list"]
                    },
                    "verbs": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {
                            "type": "string",
                            "pattern": "^[a-z][a-z0-9_]*$"
                        },
                        "description": "Supported action verbs for this capability",
                        "examples": [["start", "stop", "shutdown"], ["list"], ["cycle"]]
                    },
                    "targets": {
                        "type": "array", 
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {
                            "type": "string",
                            "pattern": "^[a-z][a-z0-9_]*$"
                        },
                        "description": "Target types this capability can operate on",
                        "examples": [["vm"], ["host"], ["vm", "host"]]
                    },
                    "dry_run": {
                        "type": "string",
                        "enum": ["required", "optional", "not_supported"],
                        "default": "optional",
                        "description": "Dry run support level for this capability"
                    }
                }
            }
        },
        "defaults": {
            "type": "object",
            "description": "Default configuration values",
            "additionalProperties": True,
            "examples": [
                {
                    "http": {
                        "timeout_s": 5,
                        "retries": 2,
                        "verify_tls": True
                    },
                    "heartbeat_interval_s": 120
                }
            ]
        },
        "test": {
            "type": "object",
            "description": "Test configuration for validating connections",
            "required": ["method"],
            "additionalProperties": False,
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["http", "tcp", "driver"],
                    "description": "Test method to use"
                },
                "http": {
                    "type": "object",
                    "description": "HTTP test configuration",
                    "required": ["request", "success_when"],
                    "additionalProperties": False,
                    "properties": {
                        "request": {
                            "type": "object",
                            "required": ["method", "path"],
                            "additionalProperties": False,
                            "properties": {
                                "method": {
                                    "type": "string",
                                    "enum": ["GET", "POST", "PUT", "DELETE", "HEAD"],
                                    "description": "HTTP method"
                                },
                                "path": {
                                    "type": "string",
                                    "description": "Request path"
                                },
                                "headers": {
                                    "type": "object",
                                    "additionalProperties": {"type": "string"},
                                    "description": "Additional headers"
                                }
                            }
                        },
                        "success_when": {
                            "type": "string",
                            "description": "Expression defining success condition",
                            "examples": ["status == 200", "status >= 200 and status < 400"]
                        }
                    }
                },
                "tcp": {
                    "type": "object",
                    "description": "TCP test configuration",
                    "required": ["port"],
                    "additionalProperties": False,
                    "properties": {
                        "port": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 65535,
                            "description": "TCP port to test"
                        },
                        "timeout_s": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 30,
                            "default": 5,
                            "description": "Connection timeout in seconds"
                        }
                    }
                }
            }
        }
    }
}


def validate_plugin_manifest(manifest_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a plugin manifest against the schema.
    
    Args:
        manifest_data: Parsed YAML data to validate
        
    Returns:
        Validation result with success/errors
    """
    import jsonschema
    from jsonschema import Draft202012Validator
    
    try:
        validator = Draft202012Validator(PLUGIN_MANIFEST_SCHEMA)
        errors = list(validator.iter_errors(manifest_data))
        
        if errors:
            return {
                "valid": False,
                "errors": [
                    {
                        "path": ".".join(str(p) for p in error.absolute_path),
                        "message": error.message,
                        "value": error.instance
                    }
                    for error in errors
                ]
            }
        
        return {"valid": True, "errors": []}
        
    except Exception as e:
        return {
            "valid": False,
            "errors": [{"path": "", "message": f"Schema validation failed: {str(e)}", "value": None}]
        }


def validate_capability_conformance(capabilities: list, driver_methods: list) -> Dict[str, Any]:
    """
    Validate that driver methods exist for all declared capabilities (Option A).
    
    Args:
        capabilities: List of capability objects from manifest
        driver_methods: List of method names from driver class
        
    Returns:
        Validation result with conformance details
    """
    errors = []
    
    for capability in capabilities:
        capability_id = capability.get("id", "")
        # Map capability.id to method name: dots become underscores  
        expected_method = capability_id.replace(".", "_")
        
        if expected_method not in driver_methods:
            errors.append({
                "capability_id": capability_id,
                "expected_method": expected_method,
                "message": f"Driver method '{expected_method}' not found for capability '{capability_id}'"
            })
    
    return {
        "conformant": len(errors) == 0,
        "errors": errors,
        "required_methods": [cap.get("id", "").replace(".", "_") for cap in capabilities]
    }