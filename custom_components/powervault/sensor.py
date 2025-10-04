"""Support for powervault sensors."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import start_of_local_day
from powervaultpy import PowerVault

from .const import DOMAIN, POWERVAULT_COORDINATOR
from .entity import PowervaultEntity
from .models import PowervaultRuntimeData

_LOGGER = logging.getLogger(__name__)

# @dataclass
# class PowervaultRequiredKeysMixin:
#     """Mixin for required keys."""

#     value_fn: Callable[[Meter], float]


# @dataclass
# class PowervaultSensorEntityDescription(
#     SensorEntityDescription, PowervaultRequiredKeysMixin
# ):
#     """Describes Powervault entity."""


# def _get_meter_power(meter: Meter) -> float:
#     """Get the current value in kW."""
#     return meter.get_power(precision=3)


# def _get_meter_frequency(meter: Meter) -> float:
#     """Get the current value in Hz."""
#     return round(meter.frequency, 1)


# def _get_meter_total_current(meter: Meter) -> float:
#     """Get the current value in A."""
#     return meter.get_instant_total_current()


# def _get_meter_average_voltage(meter: Meter) -> float:
#     """Get the current value in V."""
#     return round(meter.average_voltage, 1)

energy_sensor_names = [
    ["batteryInputFromGrid", "Battery Input From Grid"],
    ["batteryInputFromSolar", "Battery Input From Solar"],
    ["batteryOutputConsumedByHome", "Battery Output Consumed By Home"],
    ["batteryOutputExported", "Battery Output Exported"],
    ["homeConsumed", "Home Consumed"],
    ["gridConsumedByHome", "Grid Consumed By Home"],
    ["solarConsumedByHome", "Solar Consumed By Home"],
    ["solarExported", "Solar Exported"],
    ["instant_battery", "Instant Battery"],
    ["instant_demand", "Instant Demand"],
    ["instant_grid", "Instant Grid"],
    ["solarGenerated", "Solar Generated"],
    ["solarConsumption", "Solar Consumption"],
    ["instant_solar", "Instant Solar"],
]

power_sensor_names = [
    ["batteryInputFromGrid", "Total Battery Input From Grid"],
    ["batteryInputFromSolar", "Total Battery Input From Solar"],
    ["batteryOutputConsumedByHome", "Total Battery Output Consumed By Home"],
    ["batteryOutputExported", "Total Battery Output Exported"],
    ["homeConsumed", "Total Home Consumed"],
    ["gridConsumedByHome", "Total Grid Consumed By Home"],
    ["solarConsumedByHome", "Total Solar Consumed By Home"],
    ["solarExported", "Total Solar Exported"],
    ["solarGenerated", "Total Solar Generated"],
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the powerwall sensors."""
    powervault_data: PowerVault = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = powervault_data[POWERVAULT_COORDINATOR]
    assert coordinator is not None
    entities: list[PowervaultEntity] = [
        PowervaultChargeSensor(powervault_data),
    ]

    # if data.backup_reserve is not None:
    #     entities.append(PowerWallBackupReserveSensor(powerwall_data))

    # for meter in data.meters.meters:
    #     entities.append(PowerWallExportSensor(powerwall_data, meter))
    #     entities.append(PowerWallImportSensor(powerwall_data, meter))
    for sensor in energy_sensor_names:
        _LOGGER.debug(f"Adding sensor {sensor[0]}")
        entities.append(PowervaultEnergySensor(powervault_data, sensor[0], sensor[1]))

    for sensor in power_sensor_names:
        _LOGGER.debug(f"Adding sensor {sensor[0]}")
        entities.append(PowervaultPowerSensor(powervault_data, sensor[0], sensor[1]))

    async_add_entities(entities)


class PowervaultChargeSensor(PowervaultEntity, SensorEntity):
    """Representation of an Powervault charge sensor."""

    _attr_name = "Powervault Charge"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY

    @property
    def unique_id(self) -> str:
        """Device Uniqueid."""
        return f"{self.base_unique_id}_charge"

    @property
    def native_value(self) -> float | None:
        """Get the current value in percentage."""
        try:
            return round(self.data.charge)  # type: ignore[no-any-return]
        except (KeyError, TypeError):
            pass
        return None


class PowervaultEnergySensor(PowervaultEntity, SensorEntity):
    """Representation of an Powervault Energy sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER

    def __init__(
        self,
        powervault_data: PowervaultRuntimeData,
        json_key: str,
        description: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(powervault_data)
        self._attr_name = f"Powervault {description}"
        self._attr_unique_id = f"{self.base_unique_id}_{json_key}"
        self.json_key = json_key

    @property
    def native_value(self) -> float | None:
        """Get the current value in percentage."""
        try:
            return round(getattr(self.data, self.json_key) / 1000)  # type: ignore[no-any-return]
        except (KeyError, TypeError):
            pass
        return None


class PowervaultPowerSensor(PowervaultEntity, SensorEntity):
    """Representation of an Powervault Power sensor."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY

    def __init__(
        self,
        powervault_data: PowervaultRuntimeData,
        json_key: str,
        description: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(powervault_data)
        self._attr_name = f"Powervault {description}"
        self._attr_unique_id = f"{self.base_unique_id}_total{json_key}"
        self.json_key = json_key

    @property
    def native_value(self) -> float | None:
        """Get the current value in percentage."""
        try:
            return round(self.data.totals[self.json_key] / 1000, 2)  # type: ignore[no-any-return]
        except (KeyError, TypeError):
            pass
        return None

    @property
    def last_reset(self) -> datetime | None:
        """Return the time when the sensor was last reset (start of today)."""
        return start_of_local_day()  # type: ignore[no-any-return]
