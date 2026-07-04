"""The powervault integration models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias, TypedDict

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from powervaultpy import PowerVault
from requests import Session

if TYPE_CHECKING:
    from .__init__ import PowervaultDataManager


TelemetryValue: TypeAlias = str | int | float


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
    battery_state: str | None
    totals: dict
    common_telemetry: dict[str, TelemetryValue]
    battery_diagnostics: dict[str, TelemetryValue]
    detailed_battery: dict[str, dict[str, TelemetryValue]]


class PowervaultRuntimeData(TypedDict):
    """Run time data for the powerwall."""

    coordinator: DataUpdateCoordinator[PowervaultData] | None
    api_instance: PowerVault
    manager: PowervaultDataManager
    base_info: PowervaultBaseInfo
    api_changed: bool
    http_session: Session
