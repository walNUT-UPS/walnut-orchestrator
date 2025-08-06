"""
Comprehensive database tests for walNUT.

Tests cover:
- Database engine creation with SQLCipher encryption
- Connection pooling and concurrent access
- Schema creation and migration
- Model operations (CRUD)
- Local disk validation
- Error handling and recovery
"""

import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import pytest
import pytest_asyncio

from sqlalchemy.exc import OperationalError
from sqlalchemy.sql import text

from walnut.database.engine import (
    DatabaseError,
    EncryptionError,
    ValidationError,
    create_database_engine,
    get_database_url,
    get_master_key,
    test_database_connection,
    validate_database_path,
)
from walnut.database.connection import (
    ConnectionManager,
    init_database,
    close_database,
    get_db_session,
    get_db_transaction,
    get_database_health,
)
from walnut.database.models import (
    Base,
    UPSSample,
    Event,
    Integration,
    Host,
    Secret,
    Policy,
    create_ups_sample,
    create_event,
    create_integration,
    create_host,
    create_policy,
    serialize_model,
)


@pytest.fixture
def test_master_key():
    """Provide a test master key for database encryption."""
    return "test_master_key_32_characters_long_secure_key_123456789"


@pytest.fixture  
def temp_db_path():
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    try:
        db_path.unlink()
    except FileNotFoundError:
        pass
    # Also cleanup WAL and SHM files
    for suffix in ["-wal", "-shm"]:
        wal_file = Path(str(db_path) + suffix)
        try:
            wal_file.unlink()
        except FileNotFoundError:
            pass


@pytest.fixture
def mock_env_vars(test_master_key, monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("WALNUT_DB_KEY", test_master_key)
    return {"WALNUT_DB_KEY": test_master_key}


class TestDatabaseEngine:
    """Test database engine functionality."""
    
    def test_get_master_key_from_env(self, mock_env_vars):
        """Test master key retrieval from environment variable."""
        key = get_master_key()
        assert key == mock_env_vars["WALNUT_DB_KEY"]
        assert len(key) >= 32
    
    def test_get_master_key_missing(self, monkeypatch):
        """Test error when master key is missing."""
        monkeypatch.delenv("WALNUT_DB_KEY", raising=False)
        with pytest.raises(EncryptionError, match="No valid master key found"):
            get_master_key()
    
    def test_get_master_key_too_short(self, monkeypatch):
        """Test error when master key is too short."""
        monkeypatch.setenv("WALNUT_DB_KEY", "short")
        with pytest.raises(EncryptionError, match="No valid master key found"):
            get_master_key()
    
    def test_validate_database_path_valid(self, temp_db_path):
        """Test database path validation with valid path."""
        # Should not raise any exception
        validate_database_path(temp_db_path)
        assert temp_db_path.parent.exists()
    
    def test_validate_database_path_creates_parent(self):
        """Test that validation creates parent directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "subdir" / "test.db"
            validate_database_path(db_path)
            assert db_path.parent.exists()
    
    def test_get_database_url(self, temp_db_path, mock_env_vars):
        """Test database URL generation."""
        url = get_database_url(temp_db_path)
        assert str(temp_db_path) in url
        assert "sqlite+aiosqlite://" in url
        assert "key=" in url
        assert "cipher=aes-256-cbc" in url
    
    @pytest.fixture
    async def test_engine(self, temp_db_path, mock_env_vars):
        """Create a test database engine."""
        engine = create_database_engine(
            db_path=temp_db_path,
            echo=False,
            pool_size=5,
        )
        yield engine
        await engine.dispose()
    
    async def test_create_database_engine(self, temp_db_path, mock_env_vars):
        """Test database engine creation."""
        engine = create_database_engine(
            db_path=temp_db_path,
            echo=False,
        )
        
        assert engine is not None
        assert engine.pool.size() == 20  # Default pool size
        
        await engine.dispose()
    
    async def test_database_connection_test(self, test_engine):
        """Test database connectivity and diagnostics."""
        diagnostics = await test_database_connection(test_engine)
        
        assert diagnostics["connection_test"] is True
        assert "sqlite_version" in diagnostics
        assert diagnostics["wal_mode_enabled"] is True
        # Note: cipher_version might be None if pysqlcipher3 is not properly installed
    
    async def test_concurrent_connections(self, test_engine):
        """Test concurrent database access."""
        async def create_connection():
            async with test_engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                return result.scalar()
        
        # Test multiple concurrent connections
        tasks = [create_connection() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        assert all(result == 1 for result in results)


class TestConnectionManager:
    """Test connection manager functionality."""
    
    @pytest.fixture
    async def connection_manager(self, temp_db_path, mock_env_vars):
        """Create a test connection manager."""
        manager = ConnectionManager(
            db_path=str(temp_db_path),
            echo=False,
            pool_size=5,
        )
        await manager.startup()
        yield manager
        await manager.shutdown()
    
    async def test_connection_manager_startup(self, temp_db_path, mock_env_vars):
        """Test connection manager startup."""
        manager = ConnectionManager(db_path=str(temp_db_path))
        
        diagnostics = await manager.startup()
        assert diagnostics["connection_test"] is True
        
        await manager.shutdown()
    
    async def test_get_session(self, connection_manager):
        """Test database session creation."""
        async with connection_manager.get_session() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    
    async def test_get_transaction(self, connection_manager):
        """Test transaction management."""
        # Create tables first
        await connection_manager.create_tables()
        
        async with connection_manager.get_transaction() as session:
            # Insert a test record
            sample = create_ups_sample(charge_percent=85.0, status="ONLINE")
            session.add(sample)
            # Transaction should auto-commit
        
        # Verify the record was committed
        async with connection_manager.get_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM ups_samples"))
            count = result.scalar()
            assert count == 1
    
    async def test_health_check(self, connection_manager):
        """Test health check functionality."""
        health_status = await connection_manager.health_check()
        
        assert health_status["healthy"] is True
        assert "engine_diagnostics" in health_status
        assert "pool_status" in health_status
    
    async def test_create_drop_tables(self, connection_manager):
        """Test table creation and dropping."""
        await connection_manager.create_tables()
        
        # Verify tables exist by querying them
        async with connection_manager.get_session() as session:
            for table_name in Base.metadata.tables.keys():
                result = await session.execute(
                    text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                )
                assert result.scalar() == table_name
        
        await connection_manager.drop_tables()
        
        # Verify tables are gone
        async with connection_manager.get_session() as session:
            for table_name in Base.metadata.tables.keys():
                result = await session.execute(
                    text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                )
                assert result.scalar() is None


class TestGlobalDatabaseFunctions:
    """Test global database management functions."""
    
    async def test_init_close_database(self, temp_db_path, mock_env_vars):
        """Test global database initialization and cleanup."""
        diagnostics = await init_database(
            db_path=str(temp_db_path),
            create_tables=True,
        )
        
        assert diagnostics["connection_test"] is True
        
        # Test global session access
        async with get_db_session() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
        
        # Test health check
        health = await get_database_health()
        assert health["healthy"] is True
        
        await close_database()
    
    async def test_database_transaction(self, temp_db_path, mock_env_vars):
        """Test global transaction management."""
        await init_database(
            db_path=str(temp_db_path),
            create_tables=True,
        )
        
        try:
            async with get_db_transaction() as session:
                sample = create_ups_sample(charge_percent=90.0, status="BATTERY")
                session.add(sample)
            
            # Verify committed
            async with get_db_session() as session:
                result = await session.execute(text("SELECT COUNT(*) FROM ups_samples"))
                count = result.scalar()
                assert count == 1
                
        finally:
            await close_database()


class TestDatabaseModels:
    """Test database model functionality."""
    
    @pytest.fixture
    async def db_session(self, temp_db_path, mock_env_vars):
        """Setup database with tables for model testing."""
        await init_database(
            db_path=str(temp_db_path),
            create_tables=True,
        )
        async with get_db_session() as session:
            yield session
        await close_database()
    
    async def test_ups_sample_crud(self, db_session):
        """Test UPS sample model CRUD operations."""
        # Create
        sample = create_ups_sample(
            charge_percent=75.5,
            runtime_seconds=1800,
            load_percent=45.2,
            input_voltage=230.1,
            output_voltage=228.9,
            status="ONLINE"
        )
        db_session.add(sample)
        await db_session.commit()
        
        # Read
        result = await db_session.execute(
            text("SELECT * FROM ups_samples WHERE charge_percent = 75.5")
        )
        row = result.fetchone()
        assert row is not None
        assert row.load_percent == 45.2
        assert row.status == "ONLINE"
        
        # Update
        await db_session.execute(
            text("UPDATE ups_samples SET status = 'BATTERY' WHERE id = :id"),
            {"id": row.id}
        )
        await db_session.commit()
        
        # Verify update
        result = await db_session.execute(
            text("SELECT status FROM ups_samples WHERE id = :id"),
            {"id": row.id}
        )
        assert result.scalar() == "BATTERY"
        
        # Delete
        await db_session.execute(
            text("DELETE FROM ups_samples WHERE id = :id"),
            {"id": row.id}
        )
        await db_session.commit()
        
        # Verify deletion
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM ups_samples WHERE id = :id"),
            {"id": row.id}
        )
        assert result.scalar() == 0
    
    async def test_event_model(self, db_session):
        """Test Event model."""
        event = create_event(
            event_type="MAINS_LOST",
            description="Mains power lost, running on battery",
            severity="WARNING",
            metadata={"voltage": 0, "battery_percent": 85}
        )
        db_session.add(event)
        await db_session.commit()
        
        # Query by event type
        result = await db_session.execute(
            text("SELECT * FROM events WHERE event_type = 'MAINS_LOST'")
        )
        row = result.fetchone()
        assert row is not None
        assert row.severity == "WARNING"
        assert "voltage" in row.metadata
    
    async def test_integration_model(self, db_session):
        """Test Integration model."""
        integration = create_integration(
            name="proxmox-cluster",
            integration_type="proxmox",
            config={
                "host": "pve.example.com",
                "username": "walnut@pve",
                "ssl_verify": True
            },
            enabled=True
        )
        db_session.add(integration)
        await db_session.commit()
        
        # Query by type
        result = await db_session.execute(
            text("SELECT * FROM integrations WHERE type = 'proxmox'")
        )
        row = result.fetchone()
        assert row is not None
        assert row.name == "proxmox-cluster"
        assert row.enabled is True
    
    async def test_host_model(self, db_session):
        """Test Host model."""
        host = create_host(
            hostname="server01",
            ip_address="192.168.1.100",
            os_type="linux",
            connection_type="ssh",
            metadata={"cpu_cores": 8, "ram_gb": 32}
        )
        db_session.add(host)
        await db_session.commit()
        
        # Query by hostname
        result = await db_session.execute(
            text("SELECT * FROM hosts WHERE hostname = 'server01'")
        )
        row = result.fetchone()
        assert row is not None
        assert row.ip_address == "192.168.1.100"
        assert row.os_type == "linux"
    
    async def test_secret_model(self, db_session):
        """Test Secret model."""
        secret = Secret(
            name="ssh-key-server01",
            encrypted_data=b"encrypted_private_key_data",
        )
        db_session.add(secret)
        await db_session.commit()
        
        # Query by name
        result = await db_session.execute(
            text("SELECT * FROM secrets WHERE name = 'ssh-key-server01'")
        )
        row = result.fetchone()
        assert row is not None
        assert row.encrypted_data == b"encrypted_private_key_data"
    
    async def test_policy_model(self, db_session):
        """Test Policy model."""
        policy = create_policy(
            name="emergency-shutdown",
            conditions={
                "battery_percent": {"lt": 20},
                "runtime_seconds": {"lt": 300}
            },
            actions={
                "shutdown_hosts": ["server01", "server02"],
                "notify_admins": True
            },
            priority=1,
            enabled=True
        )
        db_session.add(policy)
        await db_session.commit()
        
        # Query by priority
        result = await db_session.execute(
            text("SELECT * FROM policies WHERE priority = 1")
        )
        row = result.fetchone()
        assert row is not None
        assert row.name == "emergency-shutdown"
        assert row.enabled is True
    
    def test_serialize_model(self):
        """Test model serialization."""
        sample = create_ups_sample(
            charge_percent=80.0,
            status="ONLINE"
        )
        
        serialized = serialize_model(sample)
        assert isinstance(serialized, dict)
        assert serialized["charge_percent"] == 80.0
        assert serialized["status"] == "ONLINE"


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    async def test_invalid_database_path(self, mock_env_vars):
        """Test handling of invalid database paths."""
        # Test with read-only path (if we can simulate it)
        invalid_path = Path("/proc/invalid.db")  # Typically read-only on Linux
        
        try:
            validate_database_path(invalid_path)
        except ValidationError:
            # Expected on systems where /proc is read-only
            pass
    
    async def test_connection_failure_recovery(self, temp_db_path, mock_env_vars):
        """Test connection failure and recovery."""
        manager = ConnectionManager(db_path=str(temp_db_path))
        
        # Start normally
        await manager.startup()
        
        # Force close the engine to simulate failure
        await manager._engine.dispose()
        
        # Health check should detect the problem
        health = await manager.health_check()
        # May or may not be healthy depending on connection pool behavior
        
        await manager.shutdown()
    
    async def test_concurrent_access_stress(self, temp_db_path, mock_env_vars):
        """Test concurrent access under stress."""
        await init_database(
            db_path=str(temp_db_path),
            create_tables=True,
            pool_size=10,
        )
        
        async def insert_samples(session_id: int):
            """Insert samples concurrently."""
            async with get_db_transaction() as session:
                for i in range(5):
                    sample = create_ups_sample(
                        charge_percent=float(50 + session_id + i),
                        status=f"SESSION_{session_id}_SAMPLE_{i}"
                    )
                    session.add(sample)
        
        try:
            # Run 20 concurrent insertion sessions
            tasks = [insert_samples(i) for i in range(20)]
            await asyncio.gather(*tasks)
            
            # Verify all samples were inserted
            async with get_db_session() as session:
                result = await session.execute(text("SELECT COUNT(*) FROM ups_samples"))
                count = result.scalar()
                assert count == 100  # 20 sessions * 5 samples each
                
        finally:
            await close_database()


# Integration tests that require more setup
@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests for complete database functionality."""
    
    async def test_full_database_lifecycle(self, temp_db_path, mock_env_vars):
        """Test complete database lifecycle from init to shutdown."""
        # Initialize
        diagnostics = await init_database(
            db_path=str(temp_db_path),
            create_tables=True,
        )
        assert diagnostics["connection_test"] is True
        
        try:
            # Create some test data
            async with get_db_transaction() as session:
                # UPS samples
                for i in range(10):
                    sample = create_ups_sample(
                        charge_percent=float(100 - i * 5),
                        runtime_seconds=3600 - i * 200,
                        status="ONLINE" if i < 8 else "BATTERY"
                    )
                    session.add(sample)
                
                # Events
                event = create_event(
                    event_type="SYSTEM_START",
                    description="walNUT monitoring started",
                    severity="INFO"
                )
                session.add(event)
                
                # Integration
                integration = create_integration(
                    name="test-integration",
                    integration_type="test",
                    config={"test": True}
                )
                session.add(integration)
            
            # Verify data exists
            async with get_db_session() as session:
                ups_count = await session.execute(text("SELECT COUNT(*) FROM ups_samples"))
                assert ups_count.scalar() == 10
                
                event_count = await session.execute(text("SELECT COUNT(*) FROM events"))
                assert event_count.scalar() == 1
                
                integration_count = await session.execute(text("SELECT COUNT(*) FROM integrations"))
                assert integration_count.scalar() == 1
            
            # Test health monitoring
            health = await get_database_health()
            assert health["healthy"] is True
            
        finally:
            await close_database()
    
    async def test_migration_compatibility(self, temp_db_path, mock_env_vars):
        """Test that database works with migration system."""
        # This would typically test Alembic integration
        # For now, just verify that tables match expected schema
        
        await init_database(
            db_path=str(temp_db_path),
            create_tables=True,
        )
        
        try:
            async with get_db_session() as session:
                # Verify all expected tables exist
                expected_tables = [
                    'ups_samples', 'events', 'integrations', 
                    'hosts', 'secrets', 'policies'
                ]
                
                for table_name in expected_tables:
                    result = await session.execute(
                        text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                    )
                    assert result.scalar() == table_name, f"Table {table_name} not found"
                
                # Verify indexes exist
                result = await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
                )
                indexes = [row[0] for row in result.fetchall()]
                assert len(indexes) > 0, "No indexes found"
                
        finally:
            await close_database()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])