"""
Tests for the NUT polling service.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from walnut.nut.models import UPSData
from walnut.nut.poller import NUTPoller


@pytest.fixture
def mock_nut_client():
    """Fixture to mock the NUTClient."""
    with patch('walnut.nut.poller.NUTClient') as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_client_instance.get_vars.return_value = {
            "battery.charge": "100",
            "battery.runtime": "3600",
            "ups.load": "50",
            "input.voltage": "120",
            "output.voltage": "120",
            "ups.status": "OL",
        }
        mock_client_class.return_value = mock_client_instance
        yield mock_client_instance


@pytest.fixture
def mock_db_session():
    """Fixture to mock the database session."""
    @asynccontextmanager
    async def get_session_mock():
        yield mock_session

    with patch('walnut.nut.poller.get_db_transaction') as mock_get_transaction:
        mock_session = AsyncMock()
        mock_get_transaction.return_value = get_session_mock()
        yield mock_session


@pytest.mark.asyncio
async def test_poller_initialization():
    """Test poller initialization."""
    poller = NUTPoller("myups")
    assert poller.ups_name == "myups"
    assert poller._task is None
    assert poller.previous_data is None


@pytest.mark.asyncio
async def test_poller_start_stop(mock_nut_client):
    """Test the start and stop methods of the poller."""
    poller = NUTPoller("myups")

    with patch('asyncio.create_task') as mock_create_task:
        # To prevent the test from hanging, we'll mock the loop
        poller._poll_loop = AsyncMock()

        await poller.start()
        mock_create_task.assert_called_once_with(poller._poll_loop())

        mock_task = mock_create_task.return_value
        await poller.stop()

        # Assert that the task was cancelled
        mock_task.cancel.assert_called_once()


@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock)
async def test_poll_loop_single_run(mock_sleep, mock_nut_client, mock_db_session):
    """Test a single iteration of the polling loop."""
    poller = NUTPoller("myups")

    async def stop_loop(*args, **kwargs):
        poller._should_stop.set()

    mock_sleep.side_effect = stop_loop

    await poller._poll_loop()

    mock_nut_client.get_vars.assert_called_once_with("myups")
    mock_db_session.add.assert_called()
    assert poller.previous_data is not None
    assert poller.previous_data.battery_charge == 100


@pytest.mark.asyncio
@patch('asyncio.sleep', new_callable=AsyncMock)
async def test_event_detection(mock_sleep, mock_nut_client, mock_db_session):
    """Test that events are detected and stored."""
    poller = NUTPoller("myups")

    # First poll: online
    mock_sleep.side_effect = None
    await poller._poll_loop()

    # Second poll: on battery
    mock_nut_client.get_vars.return_value["ups.status"] = "OB"

    async def stop_loop(*args, **kwargs):
        poller._should_stop.set()
    mock_sleep.side_effect = stop_loop

    await poller._poll_loop()

    # Check that create_event was called
    # The first call to add() is the sample, the second is the event
    assert mock_db_session.add.call_count == 2 # 1 sample, 1 event
    event_call = mock_db_session.add.call_args_list[1]
    assert "MAINS_LOST" in event_call.args[0].event_type


@pytest.mark.asyncio
@patch('time.time')
@patch('asyncio.sleep', new_callable=AsyncMock)
async def test_heartbeat_timeout(mock_sleep, mock_time, mock_nut_client, mock_db_session):
    """Test heartbeat failure detection."""
    poller = NUTPoller("myups")

    # Simulate time
    start_time = time.time()
    mock_time.return_value = start_time
    poller.last_heartbeat = start_time

    # Make polling fail
    mock_nut_client.get_vars.side_effect = Exception("Connection error")

    async def stop_loop(*args, **kwargs):
        # Simulate timeout
        mock_time.return_value = start_time + 40
        poller._should_stop.set()

    mock_sleep.side_effect = stop_loop

    await poller._poll_loop()

    # Check that a critical event was logged and stored
    assert mock_db_session.add.call_count == 1
    event_call = mock_db_session.add.call_args_list[0]
    assert "NUT_SERVER_LOST" in event_call.args[0].event_type
    assert "CRITICAL" in event_call.args[0].severity


@pytest.mark.asyncio
@patch('time.time')
@patch('asyncio.sleep', new_callable=AsyncMock)
async def test_data_cleanup(mock_sleep, mock_time, mock_nut_client, mock_db_session):
    """Test cleanup of old data."""
    poller = NUTPoller("myups")

    # Simulate time
    start_time = time.time()
    mock_time.return_value = start_time
    poller.last_cleanup_time = start_time - 4000  # More than an hour ago

    async def stop_loop(*args, **kwargs):
        poller._should_stop.set()

    mock_sleep.side_effect = stop_loop

    with patch('walnut.nut.poller.delete') as mock_delete:
        await poller._poll_loop()
        mock_delete.assert_called_once()
        assert poller.last_cleanup_time == start_time
