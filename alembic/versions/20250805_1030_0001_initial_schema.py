"""Initial walNUT database schema

Revision ID: 0001
Revises: 
Create Date: 2025-08-05 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import JSON

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    
    # Create ups_samples table
    op.create_table(
        'ups_samples',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('(datetime(\'now\'))'), nullable=False),
        sa.Column('charge_percent', sa.Float(), nullable=True, comment='Battery charge percentage (0-100)'),
        sa.Column('runtime_seconds', sa.Integer(), nullable=True, comment='Estimated runtime in seconds at current load'),
        sa.Column('load_percent', sa.Float(), nullable=True, comment='UPS load percentage (0-100)'),
        sa.Column('input_voltage', sa.Float(), nullable=True, comment='Input voltage from mains power'),
        sa.Column('output_voltage', sa.Float(), nullable=True, comment='Output voltage to connected devices'),
        sa.Column('status', sa.String(length=255), nullable=True, comment='UPS status string from NUT daemon'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for ups_samples
    op.create_index('idx_ups_samples_timestamp', 'ups_samples', ['timestamp'])
    op.create_index('idx_ups_samples_charge', 'ups_samples', ['charge_percent'])
    op.create_index('idx_ups_samples_status', 'ups_samples', ['status'])
    
    # Create events table
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('(datetime(\'now\'))'), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False, comment='Event type: MAINS_LOST, MAINS_RETURNED, LOW_BATTERY, SHUTDOWN_INITIATED, etc.'),
        sa.Column('severity', sa.String(length=50), nullable=False, comment='Event severity: INFO, WARNING, CRITICAL'),
        sa.Column('description', sa.Text(), nullable=False, comment='Human-readable event description'),
        sa.Column('event_metadata', JSON(), nullable=True, comment='Additional event metadata as JSON'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for events
    op.create_index('idx_events_timestamp', 'events', ['timestamp'])
    op.create_index('idx_events_type_severity', 'events', ['event_type', 'severity'])
    op.create_index('idx_events_type_timestamp', 'events', ['event_type', 'timestamp'])
    
    # Create integrations table
    op.create_table(
        'integrations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False, comment='Unique integration name'),
        sa.Column('type', sa.String(length=100), nullable=False, comment='Integration type: proxmox, tapo, ssh, winrm, etc.'),
        sa.Column('config', JSON(), nullable=False, comment='Integration configuration (encrypted connection details)'),
        sa.Column('enabled', sa.Boolean(), nullable=False, comment='Whether integration is active'),
        sa.Column('last_success', sa.DateTime(timezone=True), nullable=True, comment='Timestamp of last successful connection'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    
    # Create indexes for integrations
    op.create_index('idx_integrations_type_enabled', 'integrations', ['type', 'enabled'])
    op.create_index('idx_integrations_enabled', 'integrations', ['enabled'])
    
    # Create hosts table
    op.create_table(
        'hosts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('hostname', sa.String(length=255), nullable=False, comment='Host name or identifier'),
        sa.Column('ip_address', sa.String(length=45), nullable=True, comment='IP address for connection'),
        sa.Column('os_type', sa.String(length=50), nullable=True, comment='Operating system: linux, windows, freebsd, etc.'),
        sa.Column('connection_type', sa.String(length=50), nullable=False, comment='Connection method: ssh, winrm, api, etc.'),
        sa.Column('credentials_ref', sa.Integer(), nullable=True, comment='Reference to secrets table for credentials'),
        sa.Column('host_metadata', JSON(), nullable=True, comment='Additional host metadata and capabilities'),
        sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=True, comment='When host was first discovered'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for hosts
    op.create_index('idx_hosts_hostname', 'hosts', ['hostname'])
    op.create_index('idx_hosts_ip', 'hosts', ['ip_address'])
    op.create_index('idx_hosts_os_type', 'hosts', ['os_type'])
    op.create_index('idx_hosts_connection_type', 'hosts', ['connection_type'])
    
    # Create secrets table
    op.create_table(
        'secrets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False, comment='Unique secret identifier'),
        sa.Column('encrypted_data', sa.LargeBinary(), nullable=False, comment='Encrypted secret data (SQLCipher handles encryption)'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(datetime(\'now\'))'), nullable=False, comment='When secret was created'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    
    # Create indexes for secrets
    op.create_index('idx_secrets_name', 'secrets', ['name'])
    op.create_index('idx_secrets_created', 'secrets', ['created_at'])
    
    # Create policies table
    op.create_table(
        'policies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False, comment='Policy name'),
        sa.Column('priority', sa.Integer(), nullable=False, comment='Policy priority (lower = higher priority)'),
        sa.Column('conditions', JSON(), nullable=False, comment='Conditions that trigger this policy (battery level, time, etc.)'),
        sa.Column('actions', JSON(), nullable=False, comment='Actions to take when conditions are met (shutdown commands, etc.)'),
        sa.Column('enabled', sa.Boolean(), nullable=False, comment='Whether policy is active'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    
    # Create indexes for policies
    op.create_index('idx_policies_enabled_priority', 'policies', ['enabled', 'priority'])
    op.create_index('idx_policies_priority', 'policies', ['priority'])


def downgrade() -> None:
    """Downgrade database schema."""
    
    # Drop tables in reverse order to handle any potential foreign key relationships
    op.drop_table('policies')
    op.drop_table('secrets')
    op.drop_table('hosts')
    op.drop_table('integrations')
    op.drop_table('events')
    op.drop_table('ups_samples')