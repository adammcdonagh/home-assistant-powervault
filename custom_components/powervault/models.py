"""The powervault integration models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from powervaultpy import PowerVault
from requests import Session


@dataclass
class PowervaultBaseInfo:
    """Base information for the powervault integration."""

    id: str
    model: str
    eprom_id: str


@dataclass
class PowervaultData:  # pylint: disable=too-many-instance-attributes
    """Point in time data for the powervault integration."""

    charge: float
    batteryInputFromGrid: float
    batteryInputFromSolar: float
    batteryOutputConsumedByHome: float
    batteryOutputExported: float
    homeConsumed: float
    gridConsumedByHome: float
    solarConsumedByHome: float
    solarExported: float
    instant_battery: float
    instant_demand: float
    instant_grid: float
    solarGenerated: float
    solarConsumption: float
    instant_solar: float
    battery_state: str
    totals: dict


class PowervaultRuntimeData(TypedDict):
    """Run time data for the powerwall."""

    coordinator: DataUpdateCoordinator[PowervaultData] | None
    api_instance: PowerVault
    base_info: PowervaultBaseInfo
    api_changed: bool
    http_session: Session
