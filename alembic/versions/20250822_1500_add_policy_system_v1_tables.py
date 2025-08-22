"""Add Policy System v1 tables - policies_v1 and policy_executions

Revision ID: add_policy_v1_tables
Revises: 20250822_1432_0022_add_oidc_oauth_support
Create Date: 2025-08-22 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = 'add_policy_v1_tables'
down_revision = '20250822_1432_0022_add_oidc_oauth_support'
branch_labels = None
depends_on = None


def upgrade():
    # Create policies_v1 table
    op.create_table('policies_v1',
    sa.Column('id', sa.String(length=36), nullable=False, comment='Policy UUID'),
    sa.Column('name', sa.String(length=255), nullable=False, comment='Policy name (min 3 chars)'),
    sa.Column('status', sa.String(length=50), nullable=False, comment='enabled|disabled|invalid'),
    sa.Column('version_int', sa.Integer(), nullable=False, comment='Version number, incremented on updates'),
    sa.Column('hash', sa.String(length=64), nullable=False, comment='SHA256 hash of normalized spec'),
    sa.Column('priority', sa.Integer(), nullable=False, comment='Execution priority (lower = higher priority)'),
    sa.Column('stop_on_match', sa.Boolean(), nullable=False, comment='Stop processing further policies on match'),
    sa.Column('dynamic_resolution', sa.Boolean(), nullable=False, comment='Re-resolve target selectors at runtime'),
    sa.Column('suppression_window_s', sa.Integer(), nullable=False, comment='Suppression window in seconds'),
    sa.Column('idempotency_window_s', sa.Integer(), nullable=False, comment='Idempotency window in seconds'),
    sa.Column('spec', sqlite.JSON(), nullable=False, comment='Original policy specification JSON'),
    sa.Column('compiled_ir', sqlite.JSON(), nullable=True, comment='Compiled intermediate representation JSON'),
    sa.Column('last_validation', sqlite.JSON(), nullable=True, comment='Last validation result with schema/compile errors'),
    sa.Column('last_dry_run', sqlite.JSON(), nullable=True, comment='Last dry-run result with transcript'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='Policy creation timestamp'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='Policy last update timestamp'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('hash')
    )
    
    # Create indexes for policies_v1
    op.create_index('idx_policies_v1_status', 'policies_v1', ['status'], unique=False)
    op.create_index('idx_policies_v1_priority', 'policies_v1', ['priority'], unique=False)
    op.create_index('idx_policies_v1_hash', 'policies_v1', ['hash'], unique=False)
    op.create_index('idx_policies_v1_enabled_priority', 'policies_v1', ['status', 'priority'], unique=False)
    op.create_index('idx_policies_v1_updated_at', 'policies_v1', ['updated_at'], unique=False)
    op.create_index('ix_policies_v1_name', 'policies_v1', ['name'], unique=False)
    
    # Create policy_executions table
    op.create_table('policy_executions',
    sa.Column('id', sa.String(length=36), nullable=False, comment='Execution UUID'),
    sa.Column('policy_id', sa.String(length=36), nullable=False, comment='Policy UUID reference'),
    sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='Execution timestamp'),
    sa.Column('severity', sa.String(length=50), nullable=False, comment='info|warn|error execution severity'),
    sa.Column('event_snapshot', sqlite.JSON(), nullable=False, comment='Snapshot of triggering event'),
    sa.Column('actions', sqlite.JSON(), nullable=False, comment='Executed actions with results'),
    sa.Column('summary', sa.Text(), nullable=False, comment='Human-readable execution summary'),
    sa.ForeignKeyConstraint(['policy_id'], ['policies_v1.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for policy_executions
    op.create_index('idx_policy_executions_policy_id', 'policy_executions', ['policy_id'], unique=False)
    op.create_index('idx_policy_executions_ts', 'policy_executions', ['ts'], unique=False)
    op.create_index('idx_policy_executions_severity', 'policy_executions', ['severity'], unique=False)
    op.create_index('idx_policy_executions_policy_ts', 'policy_executions', ['policy_id', 'ts'], unique=False)

    # Set default values for new columns
    op.execute("UPDATE policies_v1 SET status = 'disabled' WHERE status IS NULL")
    op.execute("UPDATE policies_v1 SET version_int = 1 WHERE version_int IS NULL")
    op.execute("UPDATE policies_v1 SET priority = 0 WHERE priority IS NULL")
    op.execute("UPDATE policies_v1 SET stop_on_match = 0 WHERE stop_on_match IS NULL")
    op.execute("UPDATE policies_v1 SET dynamic_resolution = 1 WHERE dynamic_resolution IS NULL")
    op.execute("UPDATE policies_v1 SET suppression_window_s = 300 WHERE suppression_window_s IS NULL")
    op.execute("UPDATE policies_v1 SET idempotency_window_s = 600 WHERE idempotency_window_s IS NULL")


def downgrade():
    # Drop indexes first
    op.drop_index('idx_policy_executions_policy_ts', table_name='policy_executions')
    op.drop_index('idx_policy_executions_severity', table_name='policy_executions')
    op.drop_index('idx_policy_executions_ts', table_name='policy_executions')
    op.drop_index('idx_policy_executions_policy_id', table_name='policy_executions')
    
    op.drop_index('ix_policies_v1_name', table_name='policies_v1')
    op.drop_index('idx_policies_v1_updated_at', table_name='policies_v1')
    op.drop_index('idx_policies_v1_enabled_priority', table_name='policies_v1')
    op.drop_index('idx_policies_v1_hash', table_name='policies_v1')
    op.drop_index('idx_policies_v1_priority', table_name='policies_v1')
    op.drop_index('idx_policies_v1_status', table_name='policies_v1')
    
    # Drop tables
    op.drop_table('policy_executions')
    op.drop_table('policies_v1')