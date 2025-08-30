#!/usr/bin/env python3
import asyncio
import os
from datetime import timezone

os.environ.setdefault("WALNUT_TESTING", "1")

from walnut.database.models import create_ups_sample
from walnut.nut.models import UPSData
from walnut.nut.poller import NUTPoller
from walnut.core import websocket_manager as ws_mod
from datetime import datetime


def assert_utc_timestamp_on_sample():
  s = create_ups_sample(charge_percent=42.0)
  assert s.timestamp.tzinfo == timezone.utc, "UPSSample timestamp must be timezone-aware UTC"


async def assert_ws_broadcast_uses_iso_utc():
  captured = {}

  async def fake_broadcast(payload):
    captured.update(payload)

  # Patch the websocket broadcast temporarily
  orig = ws_mod.websocket_manager.broadcast_ups_status
  ws_mod.websocket_manager.broadcast_ups_status = fake_broadcast
  try:
    poller = NUTPoller("testups")
    data = UPSData(battery_charge=50.0, battery_runtime=600, ups_load=10.0, input_voltage=230.0, output_voltage=230.0, status="OL")
    await poller._broadcast_ups_status(data)
  finally:
    ws_mod.websocket_manager.broadcast_ups_status = orig

  ts = captured.get("timestamp")
  assert isinstance(ts, str), "WebSocket payload timestamp should be an ISO string"
  # Should parse as aware datetime
  dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
  assert dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) == timezone.utc.utcoffset(dt), "WS timestamp must be UTC"


def main():
  assert_utc_timestamp_on_sample()
  asyncio.run(assert_ws_broadcast_uses_iso_utc())
  print("OK: backend timestamp normalization checks passed")


if __name__ == "__main__":
  main()

