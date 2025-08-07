import pytest

# Basic test for package metadata
def test_metadata():
    import walnut
    assert walnut.__version__ == "0.1.0"
    assert walnut.__author__ == "walNUT Team"
    assert walnut.__email__ == "team@walnut.io"
