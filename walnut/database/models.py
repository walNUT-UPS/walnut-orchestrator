"""
SQLAlchemy database models for walNUT UPS Management Platform.

This module defines all database tables for UPS monitoring, power events,
integrations, host management, secrets storage, and shutdown policies.
"""

import json
from datetime import datetime
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
)
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
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


class Event(Base):
    """
    Power events and system activities.
    
    Records significant events like power failures, battery warnings,
    shutdown sequences, and recovery actions.
    """
    __tablename__ = "events"
    
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
        Index("idx_events_timestamp", "timestamp"),
        Index("idx_events_type_severity", "event_type", "severity"),
        Index("idx_events_type_timestamp", "event_type", "timestamp"),
    )


class Integration(Base):
    """
    Integration configurations for external systems.
    
    Stores connection details for Proxmox, Tapo devices, SSH hosts,
    and other systems that walNUT can manage during power events.
    """
    __tablename__ = "integrations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Unique integration name"
    )
    type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Integration type: proxmox, tapo, ssh, winrm, etc."
    )
    
    # Configuration and status
    config: Mapped[Dict[str, Any]] = mapped_column(
        SQLiteJSON,
        nullable=False,
        comment="Integration configuration (encrypted connection details)"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether integration is active"
    )
    last_success: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last successful connection"
    )
    
    # Add indexes for queries
    __table_args__ = (
        Index("idx_integrations_type_enabled", "type", "enabled"),
        Index("idx_integrations_enabled", "enabled"),
    )


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


class Policy(Base):
    """
    Shutdown policies and automation rules.
    
    Defines when and how systems should be shut down based on
    battery levels, time conditions, and other criteria.
    """
    __tablename__ = "policies"
    
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
        Index("idx_policies_enabled_priority", "enabled", "priority"),
        Index("idx_policies_priority", "priority"),
    )


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


def create_event(
    event_type: str,
    description: str,
    severity: str = "INFO",
    event_metadata: Optional[Dict[str, Any]] = None,
) -> Event:
    """
    Create an event record with current timestamp.
    
    Args:
        event_type: Type of event
        description: Event description
        severity: Event severity level
        event_metadata: Additional event metadata
        
    Returns:
        Event instance
    """
    return Event(
        event_type=event_type,
        description=description,
        severity=severity,
        event_metadata=event_metadata or {},
    )


def create_integration(
    name: str,
    integration_type: str,
    config: Dict[str, Any],
    enabled: bool = True,
) -> Integration:
    """
    Create an integration configuration.
    
    Args:
        name: Integration name
        integration_type: Type of integration
        config: Configuration dictionary
        enabled: Whether integration is enabled
        
    Returns:
        Integration instance
    """
    return Integration(
        name=name,
        type=integration_type,
        config=config,
        enabled=enabled,
    )


def create_host(
    hostname: str,
    ip_address: Optional[str] = None,
    os_type: Optional[str] = None,
    connection_type: str = "ssh",
    credentials_ref: Optional[int] = None,
    host_metadata: Optional[Dict[str, Any]] = None,
) -> Host:
    """
    Create a host record.
    
    Args:
        hostname: Host name
        ip_address: IP address
        os_type: Operating system type
        connection_type: Connection method
        credentials_ref: Reference to credentials
        host_metadata: Additional metadata
        
    Returns:
        Host instance
    """
    return Host(
        hostname=hostname,
        ip_address=ip_address,
        os_type=os_type,
        connection_type=connection_type,
        credentials_ref=credentials_ref,
        host_metadata=host_metadata or {},
        discovered_at=datetime.utcnow(),
    )


def create_policy(
    name: str,
    conditions: Dict[str, Any],
    actions: Dict[str, Any],
    priority: int = 100,
    enabled: bool = True,
) -> Policy:
    """
    Create a shutdown policy.
    
    Args:
        name: Policy name
        conditions: Trigger conditions
        actions: Actions to take
        priority: Policy priority
        enabled: Whether policy is enabled
        
    Returns:
        Policy instance
    """
    return Policy(
        name=name,
        conditions=conditions,
        actions=actions,
        priority=priority,
        enabled=enabled,
    )