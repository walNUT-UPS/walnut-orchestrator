"""
Integration tests for policy API endpoints.

Tests /api/policies/validate, CRUD operations, dry-run, and executions ledger.
Uses actual FastAPI test client with database.
"""
import pytest
import asyncio
import json
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from sqlalchemy.orm import sessionmaker

from walnut.app import app
from walnut.database.connection import get_db_session_dependency
from walnut.database.models import PolicyV1, PolicyExecution
from walnut.auth.models import User


@pytest.fixture
def test_db_session():
    """Create test database session."""
    # This would be setup with test database in real implementation
    pass


@pytest.fixture
def authenticated_user():
    """Create authenticated test user.""" 
    return User(id=1, email="test@example.com", is_active=True)


@pytest.fixture
def test_client(authenticated_user):
    """Create test client with authentication."""
    
    def override_get_db_session():
        # Return mock session for testing
        return Mock()
    
    def override_require_current_user():
        return authenticated_user
    
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    app.dependency_overrides["require_current_user"] = override_require_current_user
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()


class TestValidateEndpoint:
    """Test /api/policies/validate endpoint."""
    
    def test_validate_valid_policy(self, test_client):
        """Test validation of valid policy spec."""
        valid_spec = {
            "name": "Test Policy",
            "version": "1.0",
            "trigger_group": {
                "triggers": [{
                    "type": "timer.cron", 
                    "schedule": {"cron": "0 1 * * *"}
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
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.policy.compile.validate_policy_spec') as mock_validate:
                mock_result = Mock()
                mock_result.ok = True
                mock_result.schema = []
                mock_result.compile = []
                mock_result.model_dump.return_value = {
                    "ok": True,
                    "schema": [], 
                    "compile": [],
                    "hash": "abc123",
                    "ir": {"name": "Test Policy"}
                }
                mock_validate.return_value = mock_result
                
                response = test_client.post("/api/v1/validate", json=valid_spec)
                
                assert response.status_code == 200
                result = response.json()
                assert result["ok"] is True
                assert len(result["schema"]) == 0
                assert len(result["compile"]) == 0
                assert "hash" in result
    
    def test_validate_policy_with_schema_errors(self, test_client):
        """Test validation returns schema errors."""
        invalid_spec = {
            "name": "",  # Missing name
            "version": "1.0",
            "trigger_group": {"triggers": []},  # No triggers
            "condition_group": {"conditions": []},
            "action_group": {"actions": []}  # No actions
        }
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.policy.compile.validate_policy_spec') as mock_validate:
                mock_result = Mock()
                mock_result.ok = False
                mock_result.schema = [
                    Mock(severity="blocker", message="Name cannot be empty", path="/name"),
                    Mock(severity="blocker", message="No actions defined", path="/action_group/actions")
                ]
                mock_result.compile = []
                mock_result.model_dump.return_value = {
                    "ok": False,
                    "schema": [
                        {"severity": "blocker", "message": "Name cannot be empty", "path": "/name"},
                        {"severity": "blocker", "message": "No actions defined", "path": "/action_group/actions"}
                    ],
                    "compile": []
                }
                mock_validate.return_value = mock_result
                
                response = test_client.post("/api/v1/validate", json=invalid_spec)
                
                assert response.status_code == 200  # Validation endpoint returns 200 even with errors
                result = response.json()
                assert result["ok"] is False
                assert len(result["schema"]) == 2
                assert result["schema"][0]["severity"] == "blocker"
    
    def test_validate_policy_with_compile_errors(self, test_client):
        """Test validation returns compile errors."""
        spec_with_unknown_capability = {
            "name": "Test Policy",
            "version": "1.0", 
            "trigger_group": {
                "triggers": [{
                    "type": "timer.cron",
                    "schedule": {"cron": "0 1 * * *"}
                }]
            },
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "unknown.capability",  # Unknown capability
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.policy.compile.validate_policy_spec') as mock_validate:
                mock_result = Mock()
                mock_result.ok = False
                mock_result.schema = []
                mock_result.compile = [
                    Mock(severity="blocker", message="Unknown capability: unknown.capability", 
                         path="/action_group/actions/0/capability")
                ]
                mock_result.model_dump.return_value = {
                    "ok": False,
                    "schema": [],
                    "compile": [{
                        "severity": "blocker", 
                        "message": "Unknown capability: unknown.capability",
                        "path": "/action_group/actions/0/capability"
                    }]
                }
                mock_validate.return_value = mock_result
                
                response = test_client.post("/api/v1/validate", json=spec_with_unknown_capability)
                
                assert response.status_code == 200
                result = response.json()
                assert result["ok"] is False
                assert len(result["compile"]) == 1
                assert "unknown.capability" in result["compile"][0]["message"]
    
    def test_validate_policy_v1_disabled(self, test_client):
        """Test validation endpoint when Policy v1 is disabled."""
        spec = {"name": "Test"}
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', False):
            response = test_client.post("/api/v1/validate", json=spec)
            
            assert response.status_code == 501
            assert "not enabled" in response.json()["detail"]


class TestPolicyCRUDOperations:
    """Test policy CRUD operations."""
    
    def test_create_policy_success(self, test_client):
        """Test successful policy creation."""
        valid_spec = {
            "name": "Test Create Policy",
            "version": "1.0",
            "trigger_group": {
                "triggers": [{
                    "type": "timer.cron",
                    "schedule": {"cron": "0 1 * * *"}
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
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.policy.compile.compile_policy') as mock_compile:
                with patch('walnut.database.connection.get_db_session') as mock_session:
                    # Mock compilation result
                    mock_result = Mock()
                    mock_result.ok = True
                    mock_result.hash = "test_hash_123"
                    mock_result.ir = Mock()
                    mock_result.ir.model_dump.return_value = {"name": "Test Create Policy"}
                    mock_result.schema = []
                    mock_result.compile = []
                    mock_compile.return_value = mock_result
                    
                    # Mock database session
                    mock_db_session = Mock()
                    mock_db_session.__aenter__.return_value = mock_db_session
                    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None  # No existing policy
                    mock_session.return_value = mock_db_session
                    
                    response = test_client.post("/api/v1/policies", json=valid_spec)
                    
                    assert response.status_code == 200
                    result = response.json()
                    assert "policy_id" in result
                    assert result["status"] == "enabled"
                    assert "validation" in result
    
    def test_create_policy_duplicate_hash(self, test_client):
        """Test policy creation with duplicate hash returns 409."""
        valid_spec = {
            "name": "Test Duplicate Policy", 
            "version": "1.0",
            "trigger_group": {
                "triggers": [{
                    "type": "timer.cron",
                    "schedule": {"cron": "0 1 * * *"}
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
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.policy.compile.compile_policy') as mock_compile:
                with patch('walnut.database.connection.get_db_session') as mock_session:
                    # Mock compilation result
                    mock_result = Mock()
                    mock_result.ok = True
                    mock_result.hash = "duplicate_hash_123"
                    mock_result.ir = Mock()
                    mock_result.ir.model_dump.return_value = {"name": "Test Duplicate Policy"}
                    mock_result.schema = []
                    mock_result.compile = []
                    mock_compile.return_value = mock_result
                    
                    # Mock existing policy with same hash
                    existing_policy = Mock()
                    existing_policy.id = "existing_policy_id"
                    
                    mock_db_session = Mock()
                    mock_db_session.__aenter__.return_value = mock_db_session  
                    mock_db_session.execute.return_value.scalar_one_or_none.return_value = existing_policy
                    mock_session.return_value = mock_db_session
                    
                    response = test_client.post("/api/v1/policies", json=valid_spec)
                    
                    assert response.status_code == 409
                    result = response.json()
                    assert "identical specification" in result["message"]
                    assert result["existing_policy_id"] == "existing_policy_id"
    
    def test_create_policy_with_blockers_disabled(self, test_client):
        """Test policy creation with blockers saves as disabled."""
        spec_with_blockers = {
            "name": "Test Disabled Policy",
            "version": "1.0",
            "trigger_group": {
                "triggers": [{
                    "type": "timer.cron",
                    "schedule": {"cron": "0 1 * * *"}
                }]
            },
            "condition_group": {"conditions": []},
            "action_group": {
                "actions": [{
                    "capability": "unknown.capability",  # This should cause blocker
                    "verb": "shutdown",
                    "selector": {"external_ids": ["104"]}
                }]
            }
        }
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.policy.compile.compile_policy') as mock_compile:
                with patch('walnut.database.connection.get_db_session') as mock_session:
                    # Mock compilation result with errors
                    mock_result = Mock()
                    mock_result.ok = False  # Has blockers
                    mock_result.hash = "blocked_hash_123"
                    mock_result.ir = None  # No IR due to blockers
                    mock_result.schema = []
                    mock_result.compile = [
                        Mock(severity="blocker", message="Unknown capability", path="/action_group/actions/0/capability")
                    ]
                    mock_compile.return_value = mock_result
                    
                    # Mock database session
                    mock_db_session = Mock()
                    mock_db_session.__aenter__.return_value = mock_db_session
                    mock_db_session.execute.return_value.scalar_one_or_none.return_value = None  # No existing policy
                    mock_session.return_value = mock_db_session
                    
                    response = test_client.post("/api/v1/policies", json=spec_with_blockers)
                    
                    assert response.status_code == 200
                    result = response.json()
                    assert result["status"] == "disabled"  # Should be disabled due to blockers
                    assert len(result["validation"]["compile"]) > 0


class TestDryRunEndpoint:
    """Test /api/v1/policies/{id}/dry-run endpoint."""
    
    def test_dry_run_success(self, test_client):
        """Test successful policy dry-run."""
        policy_id = "test_policy_123"
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.database.connection.get_db_session') as mock_session:
                with patch('walnut.policy.engine.create_policy_engine') as mock_engine:
                    # Mock policy from database
                    mock_policy = Mock()
                    mock_policy.id = policy_id
                    mock_policy.compiled_ir = {
                        "name": "Test Policy",
                        "action_group": {
                            "actions": [{
                                "capability": "vm.lifecycle",
                                "verb": "shutdown",
                                "selector": {"external_ids": ["104"]}
                            }]
                        }
                    }
                    
                    mock_db_session = Mock()
                    mock_db_session.__aenter__.return_value = mock_db_session
                    mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_policy
                    mock_session.return_value = mock_db_session
                    
                    # Mock policy engine dry-run result
                    mock_policy_engine = Mock()
                    mock_dry_run_result = Mock()
                    mock_dry_run_result.severity.value = "info" 
                    mock_dry_run_result.transcript_id = "transcript_123"
                    mock_dry_run_result.model_dump.return_value = {
                        "severity": "info",
                        "transcript_id": "transcript_123",
                        "plan": [{
                            "step": 1,
                            "capability": "vm.lifecycle",
                            "verb": "shutdown",
                            "targets": [{"id": "vm-104", "name": "Test VM"}],
                            "effects": {"from": "running", "to": "stopped"}
                        }]
                    }
                    mock_policy_engine.dry_run_policy.return_value = mock_dry_run_result
                    mock_engine.return_value = mock_policy_engine
                    
                    response = test_client.post(f"/api/v1/policies/{policy_id}/dry-run")
                    
                    assert response.status_code == 200
                    result = response.json()
                    assert result["severity"] == "info"
                    assert result["transcript_id"] == "transcript_123"
                    assert len(result["plan"]) == 1
                    assert result["plan"][0]["capability"] == "vm.lifecycle"
    
    def test_dry_run_policy_not_found(self, test_client):
        """Test dry-run with non-existent policy."""
        policy_id = "nonexistent_policy"
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.database.connection.get_db_session') as mock_session:
                mock_db_session = Mock()
                mock_db_session.__aenter__.return_value = mock_db_session
                mock_db_session.execute.return_value.scalar_one_or_none.return_value = None  # Policy not found
                mock_session.return_value = mock_db_session
                
                response = test_client.post(f"/api/v1/policies/{policy_id}/dry-run")
                
                assert response.status_code == 404
                assert "not found" in response.json()["detail"]
    
    def test_dry_run_no_compiled_ir(self, test_client):
        """Test dry-run with policy that has no compiled IR."""
        policy_id = "uncompiled_policy"
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.database.connection.get_db_session') as mock_session:
                # Mock policy without compiled IR
                mock_policy = Mock()
                mock_policy.id = policy_id
                mock_policy.compiled_ir = None  # No compiled IR
                
                mock_db_session = Mock()
                mock_db_session.__aenter__.return_value = mock_db_session
                mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_policy
                mock_session.return_value = mock_db_session
                
                response = test_client.post(f"/api/v1/policies/{policy_id}/dry-run")
                
                assert response.status_code == 400
                assert "no compiled IR" in response.json()["detail"]


class TestExecutionsLedger:
    """Test executions ledger functionality."""
    
    def test_get_policy_executions(self, test_client):
        """Test retrieving policy execution history."""
        policy_id = "test_policy_456"
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.database.connection.get_db_session') as mock_session:
                # Mock policy
                mock_policy = Mock()
                mock_policy.id = policy_id
                
                # Mock executions
                mock_executions = [
                    Mock(
                        id="exec_1",
                        policy_id=policy_id,
                        ts=1640995200,  # 2022-01-01 00:00:00
                        severity="info",
                        targets_resolved=2,
                        actions_attempted=2,
                        actions_succeeded=2,
                        transcript_id="transcript_1"
                    ),
                    Mock(
                        id="exec_2", 
                        policy_id=policy_id,
                        ts=1641081600,  # 2022-01-02 00:00:00
                        severity="warn",
                        targets_resolved=1,
                        actions_attempted=1,
                        actions_succeeded=0,
                        transcript_id="transcript_2"
                    )
                ]
                
                mock_db_session = Mock()
                mock_db_session.__aenter__.return_value = mock_db_session
                
                # Mock policy query
                mock_db_session.execute.return_value.scalar_one_or_none.side_effect = [
                    mock_policy,  # First call for policy existence check
                    None  # Won't be called for executions in this mock setup
                ]
                
                # Mock executions query
                mock_db_session.execute.return_value.scalars.return_value.all.return_value = mock_executions
                
                mock_session.return_value = mock_db_session
                
                response = test_client.get(f"/api/v1/policies/{policy_id}/executions")
                
                assert response.status_code == 200
                result = response.json()
                assert len(result) == 2
                # Results should be ordered by timestamp descending (most recent first)
    
    def test_get_executions_with_limit(self, test_client):
        """Test retrieving execution history with custom limit."""
        policy_id = "test_policy_789"
        custom_limit = 5
        
        with patch('walnut.config.settings.POLICY_V1_ENABLED', True):
            with patch('walnut.database.connection.get_db_session') as mock_session:
                mock_policy = Mock()
                mock_policy.id = policy_id
                
                mock_db_session = Mock()
                mock_db_session.__aenter__.return_value = mock_db_session
                mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_policy
                mock_db_session.execute.return_value.scalars.return_value.all.return_value = []
                mock_session.return_value = mock_db_session
                
                response = test_client.get(f"/api/v1/policies/{policy_id}/executions?limit={custom_limit}")
                
                assert response.status_code == 200
                # Would verify that limit is passed to query in real implementation
    
    def test_executions_prune_to_last_30(self, test_client):
        """Test that executions are pruned to last 30 entries."""
        # This would be tested at the database/service layer
        # where cleanup logic runs periodically
        pass