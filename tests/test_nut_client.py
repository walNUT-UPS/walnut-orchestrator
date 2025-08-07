"""
Tests for the NUT client wrapper.
"""

import pytest
from unittest.mock import MagicMock, patch

from walnut.nut.client import NUTClient, NUTConnectionError


@pytest.fixture
def mock_pynut_client():
    """Fixture to mock the PyNUTClient."""
    with patch('walnut.nut.client.PyNUTClient') as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance
        yield mock_client_instance


@pytest.mark.asyncio
async def test_nut_client_init():
    """Test NUTClient initialization."""
    with patch('walnut.nut.client.PyNUTClient') as mock_pynut:
        client = NUTClient(
            host="testhost",
            port=1234,
            username="testuser",
            password="testpassword"
        )
        assert client.host == "testhost"
        assert client.port == 1234
        mock_pynut.assert_called_once_with(
            host="testhost",
            port=1234,
            login="testuser",
            password="testpassword",
            debug=False
        )


@pytest.mark.asyncio
async def test_list_ups_success(mock_pynut_client):
    """Test successful listing of UPS devices."""
    mock_pynut_client.list_ups.return_value = {"ups": "Test UPS"}
    client = NUTClient()
    result = await client.list_ups()
    assert result == {"ups": "Test UPS"}
    mock_pynut_client.list_ups.assert_called_once()


@pytest.mark.asyncio
async def test_list_ups_error(mock_pynut_client):
    """Test error handling when listing UPS devices fails."""
    mock_pynut_client.list_ups.side_effect = Exception("Connection failed")
    client = NUTClient()
    with pytest.raises(NUTConnectionError, match="Failed to list UPS devices"):
        await client.list_ups()


@pytest.mark.asyncio
async def test_get_vars_success(mock_pynut_client):
    """Test successful retrieval of UPS variables."""
    mock_pynut_client.get_vars.return_value = {"battery.charge": "100"}
    client = NUTClient()
    result = await client.get_vars("myups")
    assert result == {"battery.charge": "100"}
    mock_pynut_client.get_vars.assert_called_once_with("myups")


@pytest.mark.asyncio
async def test_get_vars_error(mock_pynut_client):
    """Test error handling when getting UPS variables fails."""
    mock_pynut_client.get_vars.side_effect = Exception("UPS not found")
    client = NUTClient()
    with pytest.raises(NUTConnectionError, match="Failed to get variables for UPS 'myups'"):
        await client.get_vars("myups")


@pytest.mark.asyncio
async def test_get_var_success(mock_pynut_client):
    """Test successful retrieval of a single UPS variable."""
    mock_pynut_client.get_var.return_value = "100"
    client = NUTClient()
    result = await client.get_var("myups", "battery.charge")
    assert result == "100"
    mock_pynut_client.get_var.assert_called_once_with("myups", "battery.charge")


@pytest.mark.asyncio
async def test_get_var_error(mock_pynut_client):
    """Test error handling when getting a single UPS variable fails."""
    mock_pynut_client.get_var.side_effect = Exception("Var not found")
    client = NUTClient()
    with pytest.raises(NUTConnectionError, match="Failed to get variable 'battery.charge' for UPS 'myups'"):
        await client.get_var("myups", "battery.charge")
