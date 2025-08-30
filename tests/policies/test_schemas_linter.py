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
        "safeties": {"suppression_window": "10m"},
        "actions": [
            {
                "host_id": "1",
                "capability": "vm.lifecycle",
                "verb": "shutdown",
                "selector": {"external_ids": ["104"]},
                "options": {}
            }
        ],
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

def test_linter_no_actions(valid_policy_data):
    valid_policy_data["actions"] = []
    policy = PolicySchema(**valid_policy_data)
    result = lint_policy(policy)
    assert "At least one action is required." in result["errors"]

def test_linter_no_targets(valid_policy_data):
    valid_policy_data["actions"][0]["selector"] = {"external_ids": []}
    policy = PolicySchema(**valid_policy_data)
    result = lint_policy(policy)
    assert any("requires target identifiers" in e for e in result["errors"])

def test_large_suppression_window_warning(valid_policy_data):
    valid_policy_data["safeties"]["suppression_window"] = "48h"
    policy = PolicySchema(**valid_policy_data)
    result = lint_policy(policy)
    assert any("Suppression window is very large" in w for w in result["warnings"])
