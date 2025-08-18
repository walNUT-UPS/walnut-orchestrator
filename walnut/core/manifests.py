"""
Handles loading, validation, and parsing of integration YAML manifests.
"""
from typing import List, Optional, Any, Dict, Literal
from pydantic import BaseModel, Field, field_validator
import yaml
from pathlib import Path
import semver

class CapabilitySpec(BaseModel):
    """Defines a single capability offered by an integration."""
    id: str = Field(..., description="Capability ID, e.g., 'vm.lifecycle'.")
    verbs: List[str] = Field(..., description="List of supported actions, e.g., ['shutdown', 'reboot']")
    targets: List[str] = Field(..., description="Types of targets this capability applies to, e.g., ['vm', 'host']")
    dry_run: Literal["required", "optional", "none"] = Field("optional", description="Specifies dry-run support level.")

class SchemaSpec(BaseModel):
    """Defines the JSON-schema for connection properties."""
    connection: Dict[str, Any]

class HttpDefaults(BaseModel):
    timeout_s: int = 5
    retries: int = 2
    backoff_ms_start: int = 250
    verify_tls: bool = True

class DefaultsSpec(BaseModel):
    """Defines default operational parameters."""
    http: HttpDefaults = Field(default_factory=HttpDefaults)
    heartbeat_interval_s: int = 120

class TestSpec(BaseModel):
    """Defines how to test the integration's connectivity."""
    method: Literal["http"]
    http: Dict[str, Any]

class DriverSpec(BaseModel):
    entrypoint: str
    language: Literal["python"]
    runtime: Literal["embedded"]

class IntegrationManifest(BaseModel):
    """Pydantic model for validating an integration YAML manifest."""
    id: str = Field(..., description="Unique ID for the integration, e.g., 'walnut.proxmox.ve'.")
    name: str = Field(..., description="Human-readable name, e.g., 'Proxmox VE'.")
    version: str = Field(..., description="Semantic version of the integration manifest.")
    category: str = Field("other", description="Category for grouping integrations.")
    min_core_version: str = Field(..., description="Minimum version of walNUT core required.")

    driver: DriverSpec
    schema_def: SchemaSpec = Field(..., alias="schema")
    defaults: DefaultsSpec = Field(default_factory=DefaultsSpec)
    test: TestSpec
    capabilities: List[CapabilitySpec]

    @field_validator('version', 'min_core_version')
    def validate_semver(cls, v):
        try:
            semver.VersionInfo.parse(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a valid semantic version.")
        return v

class ManifestLoader:
    """Loads and validates integration manifests from the filesystem."""

    def __init__(self, manifest_dir: Path):
        self.manifest_dir = manifest_dir

    def load_all(self) -> List[Dict[str, Any]]:
        """Loads all valid plugin.yaml manifests from subdirectories."""
        manifests_data = []
        if not self.manifest_dir.is_dir():
            print(f"Warning: Manifest directory not found at {self.manifest_dir}")
            return []

        for filepath in self.manifest_dir.rglob("plugin.yaml"):
            try:
                manifest = self.load_from_file(filepath)
                manifests_data.append({
                    "manifest": manifest,
                    "path": filepath.parent, # The directory of the plugin
                })
            except Exception as e:
                print(f"Error loading manifest {filepath}: {e}")
        return manifests_data

    def load_from_file(self, filepath: Path) -> IntegrationManifest:
        """Loads and validates a single manifest file."""
        with open(filepath, 'r') as f:
            data = yaml.safe_load(f)

        manifest = IntegrationManifest.parse_obj(data)
        return manifest
