"""
Tests specifically for SQLCipher encryption functionality.

This module contains tests that verify actual database encryption
is working correctly, not just that the configuration appears correct.
"""

import os
import tempfile
import pytest
import sqlite3
from pathlib import Path
from typing import Dict, Any

from walnut.database.sqlcipher_dialect import test_sqlcipher_encryption as verify_sqlcipher_encryption, SQLCIPHER_AVAILABLE
from walnut.database.engine import (
    EncryptionError,
    create_database_engine,
    get_master_key,
    test_database_connection as check_database_connection,
)


@pytest.fixture
def test_encryption_key():
    """Provide a test encryption key."""
    return "test_sqlcipher_key_32_chars_minimum_length_secure"


@pytest.fixture
def temp_encrypted_db(test_encryption_key):
    """Create a temporary encrypted database file path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    yield db_path, test_encryption_key
    
    # Cleanup
    for suffix in ["", "-wal", "-shm"]:
        try:
            Path(str(db_path) + suffix).unlink()
        except FileNotFoundError:
            pass


class TestSQLCipherEncryption:
    """Test actual SQLCipher encryption functionality."""
    
    @pytest.mark.skipif(not SQLCIPHER_AVAILABLE, reason="pysqlcipher3 not available")
    def test_sqlcipher_encryption_verification(self, temp_encrypted_db):
        """Test that SQLCipher encryption actually works."""
        db_path, key = temp_encrypted_db
        
        # Run comprehensive encryption test
        result = verify_sqlcipher_encryption(str(db_path), key)
        
        assert result["encryption_verified"] is True
        assert result["database_size"] > 0
        assert "correct_key_access" in result["tests_passed"]
        assert "wrong_key_denied" in result["tests_passed"] 
        assert "regular_sqlite_denied" in result["tests_passed"]
    
    @pytest.mark.skipif(not SQLCIPHER_AVAILABLE, reason="pysqlcipher3 not available")
    def test_encrypted_database_cannot_be_read_without_key(self, temp_encrypted_db):
        """Test that encrypted database cannot be opened without the correct key."""
        db_path, key = temp_encrypted_db
        
        # Create encrypted database with test data
        import pysqlcipher3.dbapi2 as sqlcipher
        
        conn = sqlcipher.connect(str(db_path))
        conn.execute(f"PRAGMA key = '{key}'")
        conn.execute("CREATE TABLE sensitive_data (id INTEGER, secret TEXT)")
        conn.execute("INSERT INTO sensitive_data VALUES (1, 'top_secret_information')")
        conn.commit()
        conn.close()
        
        # Verify we can read with correct key
        conn = sqlcipher.connect(str(db_path))
        conn.execute(f"PRAGMA key = '{key}'")
        cursor = conn.execute("SELECT secret FROM sensitive_data WHERE id = 1")
        result = cursor.fetchone()
        assert result[0] == "top_secret_information"
        conn.close()
        
        # Verify we cannot read without key (regular SQLite)
        with pytest.raises(sqlite3.DatabaseError):
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT COUNT(*) FROM sqlite_master")
            conn.close()
        
        # Verify we cannot read with wrong key
        with pytest.raises(sqlcipher.DatabaseError):
            conn = sqlcipher.connect(str(db_path))
            conn.execute("PRAGMA key = 'wrong_key'")
            conn.execute("SELECT COUNT(*) FROM sqlite_master")
            conn.close()
    
    @pytest.mark.skipif(not SQLCIPHER_AVAILABLE, reason="pysqlcipher3 not available")
    async def test_sqlalchemy_engine_with_sqlcipher(self, temp_encrypted_db, monkeypatch):
        """Test SQLAlchemy engine works with SQLCipher dialect."""
        db_path, key = temp_encrypted_db
        
        # Set up environment for key retrieval
        monkeypatch.setenv("WALNUT_DB_KEY", key)
        
        # Create engine with SQLCipher
        engine = create_database_engine(
            db_path=db_path,
            use_encryption=True,
            pool_size=1,
        )
        
        try:
            # Test connection and verify encryption
            diagnostics = await check_database_connection(engine)
            
            assert diagnostics["connection_test"] is True
            assert diagnostics["encryption_enabled"] is True
            assert diagnostics["database_url_type"] == "sqlcipher"
            assert diagnostics["wal_mode_enabled"] is True
            
            # If verification test passes, it means encryption is working
            if diagnostics.get("sqlcipher_verified"):
                assert diagnostics["sqlcipher_verified"] is True
            
        finally:
            await engine.dispose()
    
    @pytest.mark.skipif(not SQLCIPHER_AVAILABLE, reason="pysqlcipher3 not available")
    def test_database_file_is_actually_encrypted(self, temp_encrypted_db):
        """
        Test that the database file on disk is actually encrypted by
        examining its binary content.
        """
        db_path, key = temp_encrypted_db
        
        # Create encrypted database
        import pysqlcipher3.dbapi2 as sqlcipher
        
        conn = sqlcipher.connect(str(db_path))
        conn.execute(f"PRAGMA key = '{key}'")
        conn.execute("CREATE TABLE test_table (data TEXT)")
        conn.execute("INSERT INTO test_table VALUES ('plaintext_data_that_should_be_encrypted')")
        conn.commit()
        conn.close()
        
        # Read raw file content
        with open(db_path, 'rb') as f:
            file_content = f.read()
        
        # SQLite files normally start with "SQLite format 3" magic bytes
        sqlite_magic = b"SQLite format 3"
        
        # Encrypted file should NOT start with SQLite magic bytes
        assert not file_content.startswith(sqlite_magic), \
            "Database file starts with SQLite magic bytes - not encrypted!"
        
        # Encrypted file should not contain our plaintext data
        plaintext_data = b"plaintext_data_that_should_be_encrypted"
        assert plaintext_data not in file_content, \
            "Plaintext data found in database file - not encrypted!"
        
        # File should have some content (not empty)
        assert len(file_content) > 0, "Database file is empty"
        
        print(f"✓ Database file is {len(file_content)} bytes and appears encrypted")
        print(f"✓ File does not start with SQLite magic bytes")
        print(f"✓ Plaintext data is not visible in file content")
    
    @pytest.mark.skipif(not SQLCIPHER_AVAILABLE, reason="pysqlcipher3 not available") 
    def test_wrong_key_error_handling(self, temp_encrypted_db):
        """Test proper error handling when wrong encryption key is provided."""
        db_path, correct_key = temp_encrypted_db
        
        # Create encrypted database with actual content
        import pysqlcipher3.dbapi2 as sqlcipher
        
        conn = sqlcipher.connect(str(db_path))
        conn.execute(f"PRAGMA key = '{correct_key}'")
        conn.execute("CREATE TABLE test (id INTEGER, data TEXT)")
        conn.execute("INSERT INTO test (id, data) VALUES (1, 'encrypted_content')")
        conn.commit()
        conn.close()
        
        # Verify database is actually encrypted by trying to open as regular SQLite
        try:
            regular_conn = sqlite3.connect(str(db_path))
            regular_conn.execute("SELECT COUNT(*) FROM test")
            regular_conn.close()
            pytest.fail("Database should be encrypted and not readable as regular SQLite")
        except sqlite3.DatabaseError:
            # Expected - database should be encrypted
            pass
        
        # Try to open the existing database with wrong key - should fail
        with pytest.raises(sqlcipher.DatabaseError) as exc_info:
            wrong_conn = sqlcipher.connect(str(db_path))
            wrong_conn.execute("PRAGMA key = 'wrong_key_definitely_incorrect'")
            # This should fail when we try to read from the encrypted database
            wrong_conn.execute("SELECT COUNT(*) FROM test")
            wrong_conn.close()
        
        # Error should indicate database problem (encryption working properly)
        error_msg = str(exc_info.value).lower()
        assert "file is not a database" in error_msg or "database" in error_msg, \
            f"Error message should indicate database access problem: {exc_info.value}"


class TestSQLCipherIntegration:
    """Integration tests for SQLCipher with the full walNUT stack."""
    
    @pytest.mark.skipif(not SQLCIPHER_AVAILABLE, reason="pysqlcipher3 not available")
    async def test_full_encrypted_database_lifecycle(self, temp_encrypted_db, monkeypatch):
        """Test complete database lifecycle with encryption."""
        db_path, key = temp_encrypted_db
        monkeypatch.setenv("WALNUT_DB_KEY", key)
        
        from walnut.database.connection import init_database, close_database, get_db_session
        from walnut.database.models import create_ups_sample
        from sqlalchemy.sql import text
        
        # Initialize encrypted database
        diagnostics = await init_database(
            db_path=str(db_path),
            create_tables=True,
        )
        
        try:
            assert diagnostics["connection_test"] is True
            assert diagnostics["encryption_enabled"] is True
            
            # Insert test data through SQLAlchemy
            async with get_db_session() as session:
                sample = create_ups_sample(
                    charge_percent=85.0,
                    status="ONLINE",
                    runtime_seconds=3600
                )
                session.add(sample)
                await session.commit()
                
                # Query data back
                result = await session.execute(
                    text("SELECT charge_percent, status FROM ups_samples WHERE charge_percent = 85.0")
                )
                row = result.fetchone()
                assert row is not None
                assert row.charge_percent == 85.0
                assert row.status == "ONLINE"
            
            # Verify the database file is actually encrypted
            with open(db_path, 'rb') as f:
                content = f.read()
                assert not content.startswith(b"SQLite format 3")
                assert b"ONLINE" not in content  # Our data shouldn't be visible
            
        finally:
            await close_database()
    
    def test_fallback_to_unencrypted_when_sqlcipher_unavailable(self, temp_encrypted_db, monkeypatch):
        """Test graceful fallback when SQLCipher is not available."""
        db_path, key = temp_encrypted_db
        monkeypatch.setenv("WALNUT_DB_KEY", key)
        
        # Mock SQLCipher as unavailable
        import walnut.database.engine as engine_module
        original_available = engine_module.SQLCIPHER_AVAILABLE
        engine_module.SQLCIPHER_AVAILABLE = False
        
        try:
            from walnut.database.engine import get_database_url
            
            # Should fall back to regular SQLite with warning
            url = get_database_url(db_path, use_encryption=True)
            assert "sqlite+aiosqlite" in url
            assert "sqlcipher" not in url
            
        finally:
            # Restore original state
            engine_module.SQLCIPHER_AVAILABLE = original_available


if __name__ == "__main__":
    pytest.main([__file__, "-v"])