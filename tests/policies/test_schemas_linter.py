import pytest
from walnut.policies.schemas import PolicySchema
from walnut.policies.linter import lint_policy

@pytest.fixture
def valid_policy_data():
    return {
        "name": "Test Policy",
        "priority": 128,
        "trigger": {"type": "status_transition", "from": "OL", "to": "OB", "stable_for": "15s"},
        "conditions": {"all": [], "any": []},
        "targets": {"selector": {"hosts": ["host1"]}},
        "safeties": {"suppression_window": "10m"},
        "steps": [{"type": "notify", "params": {"message": "Hello"}}],
    }

def test_valid_policy_schema(valid_policy_data):
    policy = PolicySchema(**valid_policy_data)
    assert policy.name == "Test Policy"
    assert lint_policy(policy) == {"errors": [], "warnings": []}

def test_linter_empty_name(valid_policy_data):
    valid_policy_data["name"] = ""
    policy = PolicySchema(**valid_policy_data)
    result = lint_policy(policy)
    assert "Policy name cannot be empty." in result["errors"]

def test_linter_no_steps(valid_policy_data):
    valid_policy_data["steps"] = []
    policy = PolicySchema(**valid_policy_data)
    result = lint_policy(policy)
    assert "Policy must have at least one step." in result["errors"]

def test_linter_no_targets(valid_policy_data):
    valid_policy_data["targets"]["selector"]["hosts"] = []
    policy = PolicySchema(**valid_policy_data)
    result = lint_policy(policy)
    assert "Policy has no targets and will not run on any host." in result["warnings"]

def test_linter_destructive_action_warning(valid_policy_data):
    valid_policy_data["steps"] = [{"type": "ssh.shutdown"}]
    valid_policy_data["safeties"] = {}
    policy = PolicySchema(**valid_policy_data)
    result = lint_policy(policy)
    assert "is a destructive action but has no safeties" in result["warnings"][0]
