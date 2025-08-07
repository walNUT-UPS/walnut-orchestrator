"""
Data models for NUT (Network UPS Tools) integration.

This module defines the Pydantic models for representing and validating
UPS data polled from the NUT server.
"""

from pydantic import BaseModel, Field


class UPSData(BaseModel):
    """
    Represents a snapshot of UPS data.

    All fields are optional as they may not be available from all UPS devices.
    """

    battery_charge: float | None = Field(None, alias="battery.charge")
    battery_runtime: int | None = Field(None, alias="battery.runtime")
    ups_load: float | None = Field(None, alias="ups.load")
    input_voltage: float | None = Field(None, alias="input.voltage")
    output_voltage: float | None = Field(None, alias="output.voltage")
    status: str | None = Field(None, alias="ups.status")
