"""
Event detection for NUT integration.

This module provides logic for detecting power-related events based on
changes in UPS status.
"""

from typing import List, Optional

from .models import UPSData

EVENT_MAINS_LOST = "MAINS_LOST"
EVENT_MAINS_RETURNED = "MAINS_RETURNED"
EVENT_LOW_BATTERY = "LOW_BATTERY"


def detect_events(previous_data: Optional[UPSData], current_data: UPSData) -> List[str]:
    """
    Detects power-related events by comparing the status of two UPSData objects.

    Args:
        previous_data: The previous UPS data snapshot. Can be None.
        current_data: The current UPS data snapshot.

    Returns:
        A list of event type strings that have occurred.
    """
    if previous_data is None or previous_data.status is None or current_data.status is None:
        return []

    events: List[str] = []
    prev_statuses = set(previous_data.status.split())
    current_statuses = set(current_data.status.split())

    # OL = Online, OB = On Battery, LB = Low Battery

    # Mains power lost
    if "OL" in prev_statuses and "OB" in current_statuses:
        events.append(EVENT_MAINS_LOST)

    # Mains power returned
    if "OB" in prev_statuses and "OL" in current_statuses:
        events.append(EVENT_MAINS_RETURNED)

    # Low battery condition
    if "LB" not in prev_statuses and "LB" in current_statuses:
        events.append(EVENT_LOW_BATTERY)

    return events
