"""
SQLAlchemy database models for walNUT UPS Management Platform.

This module defines all database tables for UPS monitoring, power events,
integrations, host management, secrets storage, and shutdown policies.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    LargeBinary,
    Float,
    String,
    Text,
    UniqueConstraint,
    Index,
    ForeignKey,
    desc,
)
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""
    
    # Use SQLite-compatible JSON type
    type_annotation_map = {
        dict: SQLiteJSON,
        Dict: SQLiteJSON,
        Dict[str, Any]: SQLiteJSON,
        List: SQLiteJSON,
        List[str]: SQLiteJSON,
    }


class UPSSample(Base):
    """
    UPS monitoring samples with rolling 24-hour window.
    
    Stores real-time metrics from UPS devices including battery charge,
    runtime estimates, load levels, and voltage readings.
    """
    __tablename__ = "ups_samples"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False,
        server_default=func.now(),
        index=True
    )
    
    # Battery metrics
    charge_percent: Mapped[Optional[float]] = mapped_column(
        Float, 
        nullable=True,
        comment="Battery charge percentage (0-100)"
    )
    runtime_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True, 
        comment="Estimated runtime in seconds at current load"
    )
    
    # Load and power metrics
    load_percent: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="UPS load percentage (0-100)"
    )
    input_voltage: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Input voltage from mains power"
    )
    output_voltage: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Output voltage to connected devices"
    )
    
    # UPS status and metadata
    status: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="UPS status string from NUT daemon"
    )
    
    # Add indexes for efficient queries
    __table_args__ = (
        Index("idx_ups_samples_timestamp", "timestamp"),
        Index("idx_ups_samples_charge", "charge_percent"),
        Index("idx_ups_samples_status", "status"),
    )


class LegacyEvent(Base):
    """
    Power events and system activities. (Legacy)
    
    Records significant events like power failures, battery warnings,
    shutdown sequences, and recovery actions.
    """
    __tablename__ = "legacy_events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True
    )
    
    # Event classification
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Event type: MAINS_LOST, MAINS_RETURNED, LOW_BATTERY, SHUTDOWN_INITIATED, etc."
    )
    severity: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="INFO",
        index=True,
        comment="Event severity: INFO, WARNING, CRITICAL"
    )
    
    # Event details
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable event description"
    )
    event_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        SQLiteJSON,
        nullable=True,
        comment="Additional event metadata as JSON"
    )
    
    # Add indexes for efficient event queries
    __table_args__ = (
        Index("idx_legacy_events_timestamp", "timestamp"),
        Index("idx_legacy_events_type_severity", "event_type", "severity"),
        Index("idx_legacy_events_type_timestamp", "event_type", "timestamp"),
    )


# --- Integration Framework Models ---

class IntegrationType(Base):
    """
    Stores integration types discovered from ./integrations/<slug>/ folders.
    Each type represents a validated plugin with manifest and driver.
    """
    __tablename__ = "integration_types"

    # Primary identifiers
    id: Mapped[str] = mapped_column(String(255), primary_key=True, comment="From plugin manifest id field")
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="Human-readable name")
    version: Mapped[str] = mapped_column(String(50), nullable=False, comment="Semantic version")
    min_core_version: Mapped[str] = mapped_column(String(50), nullable=False, comment="Minimum walNUT core version")
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True, comment="Integration category")
    
    # File system location and discovery
    path: Mapped[str] = mapped_column(String(1024), nullable=False, comment="Absolute path to integration folder")
    
    # Validation status and errors
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="checking", index=True, 
                                       comment="checking|valid|invalid|superseded|unavailable")
    errors: Mapped[Optional[Dict[str, Any]]] = mapped_column(SQLiteJSON, nullable=True, 
                                                           comment="Validation errors as JSON")
    
    # Parsed manifest data
    capabilities: Mapped[Dict[str, Any]] = mapped_column(SQLiteJSON, nullable=False, 
                                                        comment="Capabilities list from manifest")
    schema_connection: Mapped[Dict[str, Any]] = mapped_column(SQLiteJSON, nullable=False,
                                                             comment="Connection schema for instance creation")
    defaults: Mapped[Optional[Dict[str, Any]]] = mapped_column(SQLiteJSON, nullable=True,
                                                              comment="Default values from manifest") 
    test_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(SQLiteJSON, nullable=True,
                                                                 comment="Test configuration from manifest")
    
    # Driver information
    driver_entrypoint: Mapped[str] = mapped_column(String(255), nullable=False, 
                                                  comment="Python import path to driver class")
    
    # Audit fields
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True,
                                                                 comment="When validation last completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), 
                                                server_default=func.now(), nullable=False)

    instances: Mapped[List["IntegrationInstance"]] = relationship(back_populates="type")

    __table_args__ = (
        Index("idx_integration_types_status", "status"),
        Index("idx_integration_types_category", "category"),
        Index("idx_integration_types_last_validated", "last_validated_at"),
    )


class IntegrationInstance(Base):
    """
    A configured instance of an IntegrationType created from the Hosts tab.
    Represents a specific connection/configuration (e.g., pve-01, office-tapo-plug).
    """
    __tablename__ = "integration_instances"

    # Primary key and type reference
    instance_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_id: Mapped[str] = mapped_column(ForeignKey("integration_types.id"), nullable=False, index=True,
                                        comment="Reference to integration type")
    
    # Instance identification and display
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True,
                                     comment="Unique instance name")
    
    # Configuration data
    config: Mapped[Dict[str, Any]] = mapped_column(SQLiteJSON, nullable=False,
                                                  comment="Non-secret configuration values")
    secrets_ref: Mapped[Optional[Dict[str, Any]]] = mapped_column(SQLiteJSON, nullable=True,
                                                                 comment="References to encrypted secret fields")
    overrides: Mapped[Optional[Dict[str, Any]]] = mapped_column(SQLiteJSON, nullable=True,
                                                               comment="Instance-specific override values")
    
    # Instance state and health
    state: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False, index=True,
                                      comment="connected|degraded|error|unknown|needs_review|type_unavailable")
    last_test: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True,
                                                         comment="When connection was last tested")
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
                                                     comment="Last test connection latency")
    
    # Instance flags and metadata
    flags: Mapped[Optional[List[str]]] = mapped_column(SQLiteJSON, nullable=True,
                                                      comment="Instance flags array")
    
    # Audit fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), 
                                                server_default=func.now(), nullable=False)

    # Relationships
    type: Mapped["IntegrationType"] = relationship(back_populates="instances")
    secrets: Mapped[List["IntegrationSecret"]] = relationship(back_populates="instance", cascade="all, delete-orphan")
    targets: Mapped[List["Target"]] = relationship(back_populates="instance", cascade="all, delete-orphan")
    health_checks: Mapped[List["IntegrationHealth"]] = relationship(back_populates="instance", cascade="all, delete-orphan")
    events: Mapped[List["IntegrationEvent"]] = relationship(back_populates="instance", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_integration_instances_state", "state"),
        Index("idx_integration_instances_type_id", "type_id"),
        Index("idx_integration_instances_last_test", "last_test"),
    )


class IntegrationSecret(Base):
    """
    Field-level encrypted storage for integration instance secrets.
    """
    __tablename__ = "integration_secrets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("integration_instances.instance_id"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_type: Mapped[str] = mapped_column(String(100), nullable=False) # e.g., api_token, basic_auth
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    instance: Mapped["IntegrationInstance"] = relationship(back_populates="secrets")

    __table_args__ = (
        UniqueConstraint("instance_id", "field_name", name="uq_integration_secret_instance_field"),
    )


class Target(Base):
    """
    Discovered/managed resources that actions operate on (e.g., a VM, a host, a PoE port).
    """
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("integration_instances.instance_id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True) # e.g., vm, host, poe-port
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    attrs: Mapped[Dict[str, Any]] = mapped_column(SQLiteJSON, nullable=False)
    labels: Mapped[Dict[str, Any]] = mapped_column(SQLiteJSON, nullable=False)

    # Discovery tracking
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    instance: Mapped["IntegrationInstance"] = relationship(back_populates="targets")

    __table_args__ = (
        UniqueConstraint("instance_id", "type", "external_id", name="uq_target_instance_type_external_id"),
        Index("idx_target_labels", "labels"),
    )


class IntegrationHealth(Base):
    """
    Stores SLA metrics and health tracking data for each integration instance.
    """
    __tablename__ = "integration_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("integration_instances.instance_id"), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_details: Mapped[Optional[str]] = mapped_column(Text)

    instance: Mapped["IntegrationInstance"] = relationship(back_populates="health_checks")


class IntegrationEvent(Base):
    """
    Audit trail for integration operations (e.g., instance created, config changed, target discovered).
    """
    __tablename__ = "integration_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[Optional[int]] = mapped_column(ForeignKey("integration_instances.instance_id"), index=True) # Optional for system-wide events
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    details: Mapped[Dict[str, Any]] = mapped_column(SQLiteJSON, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    instance: Mapped[Optional["IntegrationInstance"]] = relationship(back_populates="events")


class Host(Base):
    """
    Managed hosts for coordinated shutdown.
    
    Represents servers, workstations, and other systems that walNUT
    can shut down gracefully during power events.
    """
    __tablename__ = "hosts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Host name or identifier"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),  # IPv6 compatible
        nullable=True,
        index=True,
        comment="IP address for connection"
    )
    
    # System information
    os_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Operating system: linux, windows, freebsd, etc."
    )
    connection_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ssh",
        comment="Connection method: ssh, winrm, api, etc."
    )
    
    # Security and access
    credentials_ref: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Reference to secrets table for credentials"
    )
    
    # Host metadata and discovery
    host_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        SQLiteJSON,
        nullable=True,
        comment="Additional host metadata and capabilities"
    )
    discovered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When host was first discovered"
    )
    
    # Add indexes for efficient host management
    __table_args__ = (
        Index("idx_hosts_hostname", "hostname"),
        Index("idx_hosts_ip", "ip_address"),
        Index("idx_hosts_os_type", "os_type"),
        Index("idx_hosts_connection_type", "connection_type"),
    )


class Secret(Base):
    """
    Encrypted credential storage.
    
    Stores sensitive information like passwords, API keys, and certificates
    using SQLCipher's built-in encryption.
    """
    __tablename__ = "secrets"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Unique secret identifier"
    )
    
    # Encrypted data storage
    encrypted_data: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        comment="Encrypted secret data (SQLCipher handles encryption)"
    )
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When secret was created"
    )
    
    # Add index for secret lookups
    __table_args__ = (
        Index("idx_secrets_name", "name"),
        Index("idx_secrets_created", "created_at"),
    )


class AppSetting(Base):
    """
    Simple key/value settings storage for global application settings.
    """
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Dict[str, Any]] = mapped_column(SQLiteJSON, nullable=False)


class LegacyPolicy(Base):
    """
    Shutdown policies and automation rules. (Legacy)
    
    Defines when and how systems should be shut down based on
    battery levels, time conditions, and other criteria.
    """
    __tablename__ = "legacy_policies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Policy name"
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        index=True,
        comment="Policy priority (lower = higher priority)"
    )
    
    # Policy configuration
    conditions: Mapped[Dict[str, Any]] = mapped_column(
        SQLiteJSON,
        nullable=False,
        comment="Conditions that trigger this policy (battery level, time, etc.)"
    )
    actions: Mapped[Dict[str, Any]] = mapped_column(
        SQLiteJSON,
        nullable=False,
        comment="Actions to take when conditions are met (shutdown commands, etc.)"
    )
    
    # Policy status
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether policy is active"
    )
    
    # Add indexes for policy evaluation
    __table_args__ = (
        Index("idx_legacy_policies_enabled_priority", "enabled", "priority"),
        Index("idx_legacy_policies_priority", "priority"),
    )


# New Policy and Orchestration Models

class Lock(Base):
    __tablename__ = 'locks'
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    holder: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EventBus(Base):
    __tablename__ = 'event_bus'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False) # nut|system|sim
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(SQLiteJSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    dedupe_hash: Mapped[Optional[str]] = mapped_column(Text, unique=True)

    __table_args__ = (
        Index('ix_event_bus_occurred_at', 'occurred_at'), # TODO: occurred_at should be DESC
    )


class Policy(Base):
    __tablename__ = 'policies'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=128, nullable=False)
    owner: Mapped[Optional[str]] = mapped_column(Text)
    suppression_window_sec: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    require_dry_run_first: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    global_lock: Mapped[Optional[str]] = mapped_column(Text)
    never_hosts: Mapped[Optional[Dict[str, Any]]] = mapped_column(SQLiteJSON)
    version: Mapped[str] = mapped_column(Text, default='1.0', nullable=False)
    json: Mapped[Dict[str, Any]] = mapped_column(SQLiteJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index('ix_policies_enabled_priority', 'enabled', 'priority'), # TODO: priority should be DESC
    )


class PolicyRun(Base):
    __tablename__ = 'policy_runs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey('policies.id'), nullable=False)
    event_id: Mapped[Optional[int]] = mapped_column(ForeignKey('event_bus.id'))
    status: Mapped[str] = mapped_column(Text, nullable=False) # planned|probed|dry_run|executed|suppressed|failed
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(Text)
    suppressed_by_policy_id: Mapped[Optional[int]] = mapped_column(ForeignKey('policies.id'))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(SQLiteJSON)

    policy: Mapped["Policy"] = relationship(foreign_keys=[policy_id])
    event: Mapped["EventBus"] = relationship(foreign_keys=[event_id])
    actions: Mapped[List["PolicyAction"]] = relationship(back_populates="run")


class PolicyAction(Base):
    __tablename__ = 'policy_actions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('policy_runs.id'), nullable=False)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stdout: Mapped[Optional[str]] = mapped_column(Text)
    stderr: Mapped[Optional[str]] = mapped_column(Text)
    error_code: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    run: Mapped["PolicyRun"] = relationship(back_populates="actions")


# Utility functions for working with models

def serialize_model(model: Base) -> Dict[str, Any]:
    """
    Serialize a SQLAlchemy model to a dictionary.
    
    Args:
        model: SQLAlchemy model instance
        
    Returns:
        Dictionary representation of the model
    """
    result = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        
        # Handle datetime objects
        if isinstance(value, datetime):
            result[column.name] = value.isoformat()
        # Handle JSON fields
        elif isinstance(value, (dict, list)):
            result[column.name] = value
        else:
            result[column.name] = value
            
    return result


def create_ups_sample(
    charge_percent: Optional[float] = None,
    runtime_seconds: Optional[int] = None,
    load_percent: Optional[float] = None,
    input_voltage: Optional[float] = None,
    output_voltage: Optional[float] = None,
    status: Optional[str] = None,
) -> UPSSample:
    """
    Create a UPS sample record with current timestamp.
    
    Args:
        charge_percent: Battery charge percentage
        runtime_seconds: Estimated runtime in seconds
        load_percent: UPS load percentage
        input_voltage: Input voltage
        output_voltage: Output voltage
        status: UPS status string
        
    Returns:
        UPSSample instance
    """
    return UPSSample(
        charge_percent=charge_percent,
        runtime_seconds=runtime_seconds,
        load_percent=load_percent,
        input_voltage=input_voltage,
        output_voltage=output_voltage,
        status=status,
    )




def create_host(
    hostname: str,
    ip_address: Optional[str] = None,
    os_type: Optional[str] = None,
    connection_type: str = "ssh",
    credentials_ref: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Host:
    """
    Create a host record.
    
    Args:
        hostname: Host name
        ip_address: IP address
        os_type: Operating system type
        connection_type: Connection method
        credentials_ref: Reference to credentials
        metadata: Additional metadata
        
    Returns:
        Host instance
    """
    return Host(
        hostname=hostname,
        ip_address=ip_address,
        os_type=os_type,
        connection_type=connection_type,
        credentials_ref=credentials_ref,
        host_metadata=metadata or {},
        discovered_at=datetime.now(timezone.utc),
    )


def create_event(
    event_type: str,
    description: str,
    severity: str = "INFO",
    metadata: Optional[Dict[str, Any]] = None,
) -> LegacyEvent:
    """
    Create a legacy event record.
    
    Args:
        event_type: Type of event
        description: Event description
        severity: Event severity level
        metadata: Additional event metadata
        
    Returns:
        LegacyEvent instance
    """
    return LegacyEvent(
        event_type=event_type,
        description=description,
        severity=severity,
        event_metadata=metadata or {},
    )


# ===== New Policy System Models (v1) =====

class PolicyV1(Base):
    """
    Policy System v1 table for storing compiled policy specifications.
    
    Stores policy specs, compiled IR, validation results, and execution history
    as specified in POLICY.md v1.
    """
    __tablename__ = "policies_v1"
    
    # Primary identifiers
    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="Policy UUID")
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Policy name (min 3 chars)"
    )
    
    # Status and versioning
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="disabled",
        index=True,
        comment="enabled|disabled|invalid"
    )
    version_int: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Version number, incremented on updates"
    )
    hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA256 hash of normalized spec"
    )
    
    # Policy execution configuration
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        index=True,
        comment="Execution priority (lower = higher priority)"
    )
    stop_on_match: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Stop processing further policies on match"
    )
    dynamic_resolution: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Re-resolve target selectors at runtime"
    )
    
    # Execution windows (in seconds)
    suppression_window_s: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=300,
        comment="Suppression window in seconds"
    )
    idempotency_window_s: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=600,
        comment="Idempotency window in seconds"
    )
    
    # Policy content (JSON fields)
    spec: Mapped[Dict[str, Any]] = mapped_column(
        SQLiteJSON,
        nullable=False,
        comment="Original policy specification JSON"
    )
    compiled_ir: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        SQLiteJSON,
        nullable=True,
        comment="Compiled intermediate representation JSON"
    )
    
    # Validation and dry-run results
    last_validation: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        SQLiteJSON,
        nullable=True,
        comment="Last validation result with schema/compile errors"
    )
    last_dry_run: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        SQLiteJSON,
        nullable=True,
        comment="Last dry-run result with transcript"
    )
    
    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Policy creation timestamp"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Policy last update timestamp"
    )
    
    # Relationships
    executions: Mapped[List["PolicyExecution"]] = relationship(
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="PolicyExecution.ts.desc()"
    )
    
    __table_args__ = (
        Index("idx_policies_v1_status", "status"),
        Index("idx_policies_v1_priority", "priority"),
        Index("idx_policies_v1_hash", "hash"),
        Index("idx_policies_v1_enabled_priority", "status", "priority"),
        Index("idx_policies_v1_updated_at", "updated_at"),
    )


class PolicyExecution(Base):
    """
    Policy execution history with automatic pruning to last 30 per policy.
    
    Records individual policy execution attempts, results, and summaries
    for audit and debugging purposes.
    """
    __tablename__ = "policy_executions"
    
    # Primary identifiers  
    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment="Execution UUID")
    policy_id: Mapped[str] = mapped_column(
        ForeignKey("policies_v1.id"),
        nullable=False,
        index=True,
        comment="Policy UUID reference"
    )
    
    # Execution metadata
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="Execution timestamp"
    )
    severity: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="info|warn|error execution severity"
    )
    
    # Execution context and results
    event_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        SQLiteJSON,
        nullable=False,
        comment="Snapshot of triggering event"
    )
    actions: Mapped[Dict[str, Any]] = mapped_column(
        SQLiteJSON,
        nullable=False,
        comment="Executed actions with results"
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable execution summary"
    )
    
    # Relationships
    policy: Mapped["PolicyV1"] = relationship(back_populates="executions")
    
    __table_args__ = (
        Index("idx_policy_executions_policy_id", "policy_id"),
        Index("idx_policy_executions_ts", "ts"),
        Index("idx_policy_executions_severity", "severity"),
        Index("idx_policy_executions_policy_ts", "policy_id", "ts"),
    )
