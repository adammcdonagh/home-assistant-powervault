"""Support for powervault sensors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_DETAILED_BATTERY_TELEMETRY,
    CONF_PLATFORM,
    DOMAIN,
    LEGACY_PLATFORM_P3,
    LEGACY_PLATFORM_P3X,
)
from .entity import PowervaultEntity
from .models import PowervaultRuntimeData, TelemetryValue

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


@dataclass(frozen=True)
# pylint: disable=too-many-instance-attributes
class PowervaultExtraSensorDescription:
    """Description of an additive telemetry sensor."""

    key: str
    name: str
    source: str
    unique_id_suffix: str
    child_device_key: str
    child_device_name: str
    native_unit_of_measurement: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    entity_category: EntityCategory | None = None
    precision: int | None = None
    absolute_value: bool = False


COMMON_TELEMETRY_SENSORS: tuple[PowervaultExtraSensorDescription, ...] = (
    PowervaultExtraSensorDescription(
        key="gridCurrent",
        name="Powervault Grid Current",
        source="common_telemetry",
        unique_id_suffix="telemetry_gridCurrent",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=2,
    ),
    PowervaultExtraSensorDescription(
        key="batteryCurrent",
        name="Powervault Battery Current",
        source="common_telemetry",
        unique_id_suffix="telemetry_batteryCurrent",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        precision=2,
    ),
    PowervaultExtraSensorDescription(
        key="inverterVoltage",
        name="Powervault Inverter Voltage",
        source="common_telemetry",
        unique_id_suffix="telemetry_inverterVoltage",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="inverterFrequency",
        name="Powervault Inverter Frequency",
        source="common_telemetry",
        unique_id_suffix="telemetry_inverterFrequency",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement="Hz",
        device_class=SensorDeviceClass.FREQUENCY,
        precision=2,
    ),
    PowervaultExtraSensorDescription(
        key="maxChargePower",
        name="Powervault Max Charge Power",
        source="common_telemetry",
        unique_id_suffix="telemetry_maxChargePower",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        precision=0,
    ),
    PowervaultExtraSensorDescription(
        key="maxDischargePower",
        name="Powervault Max Discharge Power",
        source="common_telemetry",
        unique_id_suffix="telemetry_maxDischargePower",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        precision=0,
        absolute_value=True,
    ),
    PowervaultExtraSensorDescription(
        key="temperature",
        name="Powervault Internal Temperature",
        source="common_telemetry",
        unique_id_suffix="telemetry_temperature",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="cpuTemperature",
        name="Powervault CPU Temperature",
        source="common_telemetry",
        unique_id_suffix="telemetry_cpuTemperature",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="vocTemperature",
        name="Powervault VOC Temperature",
        source="common_telemetry",
        unique_id_suffix="telemetry_vocTemperature",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="vocHumidity",
        name="Powervault VOC Humidity",
        source="common_telemetry",
        unique_id_suffix="telemetry_vocHumidity",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="vocCO2",
        name="Powervault VOC CO2",
        source="common_telemetry",
        unique_id_suffix="telemetry_vocCO2",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO2,
        precision=0,
    ),
    PowervaultExtraSensorDescription(
        key="vocVOC",
        name="Powervault VOC Index",
        source="common_telemetry",
        unique_id_suffix="telemetry_vocVOC",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        native_unit_of_measurement="index",
        precision=0,
    ),
    PowervaultExtraSensorDescription(
        key="actualState",
        name="Powervault Actual State",
        source="common_telemetry",
        unique_id_suffix="telemetry_actualState",
        child_device_key="telemetry",
        child_device_name="Telemetry",
        state_class=None,
    ),
)

COMMON_BATTERY_DIAGNOSTIC_SENSORS: tuple[PowervaultExtraSensorDescription, ...] = (
    PowervaultExtraSensorDescription(
        key="socAverage",
        name="Powervault Average State Of Charge",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_socAverage",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        precision=0,
    ),
)

BATTERY_GROUP_SUMMARY_SENSORS: tuple[tuple[str, str], ...] = (
    ("total_voltage", "Total Voltage"),
)

BATTERY_GROUP_AGGREGATE_SENSORS: tuple[tuple[str, str], ...] = (
    ("average_total_voltage", "Average Battery Module Total Voltage"),
    ("maximum_total_voltage", "Maximum Battery Module Total Voltage"),
)

P3_BATTERY_DIAGNOSTIC_SENSORS: tuple[PowervaultExtraSensorDescription, ...] = (
    PowervaultExtraSensorDescription(
        key="pack_temperature_min",
        name="Powervault Pack Temperature Min",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pack_temperature_min",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pack_temperature_max",
        name="Powervault Pack Temperature Max",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pack_temperature_max",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pack_temperature_avg",
        name="Powervault Pack Temperature Average",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pack_temperature_avg",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="backplane_temperature_min",
        name="Powervault Backplane Temperature Min",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_backplane_temperature_min",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="backplane_temperature_max",
        name="Powervault Backplane Temperature Max",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_backplane_temperature_max",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="backplane_temperature_avg",
        name="Powervault Backplane Temperature Average",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_backplane_temperature_avg",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="string_cell_voltage_min",
        name="Powervault String Cell Voltage Min",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_string_cell_voltage_min",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=3,
    ),
    PowervaultExtraSensorDescription(
        key="string_cell_voltage_max",
        name="Powervault String Cell Voltage Max",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_string_cell_voltage_max",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=3,
    ),
    PowervaultExtraSensorDescription(
        key="string_cell_voltage_avg",
        name="Powervault String Cell Voltage Average",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_string_cell_voltage_avg",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=3,
    ),
    PowervaultExtraSensorDescription(
        key="string_cell_temperature_min",
        name="Powervault String Cell Temperature Min",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_string_cell_temperature_min",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="string_cell_temperature_max",
        name="Powervault String Cell Temperature Max",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_string_cell_temperature_max",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="string_cell_temperature_avg",
        name="Powervault String Cell Temperature Average",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_string_cell_temperature_avg",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
)

P3X_BATTERY_DIAGNOSTIC_SENSORS: tuple[PowervaultExtraSensorDescription, ...] = (
    PowervaultExtraSensorDescription(
        key="pylontechMinCellVoltage",
        name="Powervault Pylontech Min Cell Voltage",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechMinCellVoltage",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=3,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechMaxCellVoltage",
        name="Powervault Pylontech Max Cell Voltage",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechMaxCellVoltage",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        precision=3,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechMinCellTemperature",
        name="Powervault Pylontech Min Cell Temperature",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechMinCellTemperature",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechMaxCellTemperature",
        name="Powervault Pylontech Max Cell Temperature",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechMaxCellTemperature",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechAvgCellTemperature",
        name="Powervault Pylontech Average Cell Temperature",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechAvgCellTemperature",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechMinBMSTemperature",
        name="Powervault Pylontech Min BMS Temperature",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechMinBMSTemperature",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechMaxBMSTemperature",
        name="Powervault Pylontech Max BMS Temperature",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechMaxBMSTemperature",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechAvgBMSTemperature",
        name="Powervault Pylontech Average BMS Temperature",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechAvgBMSTemperature",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechMinMOSFETTemperature",
        name="Powervault Pylontech Min MOSFET Temperature",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechMinMOSFETTemperature",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechMaxMOSFETTemperature",
        name="Powervault Pylontech Max MOSFET Temperature",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechMaxMOSFETTemperature",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
    PowervaultExtraSensorDescription(
        key="pylontechAvgMOSFETTemperature",
        name="Powervault Pylontech Average MOSFET Temperature",
        source="battery_diagnostics",
        unique_id_suffix="battery_diagnostics_pylontechAvgMOSFETTemperature",
        child_device_key="battery_diagnostics",
        child_device_name="Battery Diagnostics",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        precision=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the powerwall sensors."""
    powervault_data: PowervaultRuntimeData = hass.data[DOMAIN][config_entry.entry_id]
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

    if (platform := config_entry.data.get(CONF_PLATFORM)) in (
        LEGACY_PLATFORM_P3,
        LEGACY_PLATFORM_P3X,
    ):
        for description in _extra_sensor_descriptions(platform):
            entities.append(
                PowervaultExtraTelemetrySensor(powervault_data, description)
            )

        entities.extend(_build_battery_group_summary_sensors(powervault_data))
        entities.extend(_build_battery_group_aggregate_sensors(powervault_data))

        if config_entry.options.get(CONF_ENABLE_DETAILED_BATTERY_TELEMETRY, False):
            entities.extend(_build_detailed_battery_sensors(powervault_data))

    async_add_entities(entities)


def _extra_sensor_descriptions(
    platform: str,
) -> tuple[PowervaultExtraSensorDescription, ...]:
    """Return additive telemetry sensor descriptions for a stored platform."""
    if platform == LEGACY_PLATFORM_P3:
        return (
            *COMMON_TELEMETRY_SENSORS,
            *COMMON_BATTERY_DIAGNOSTIC_SENSORS,
            *P3_BATTERY_DIAGNOSTIC_SENSORS,
        )

    return (
        *COMMON_TELEMETRY_SENSORS,
        *COMMON_BATTERY_DIAGNOSTIC_SENSORS,
        *P3X_BATTERY_DIAGNOSTIC_SENSORS,
    )


def _build_detailed_battery_sensors(
    powervault_data: PowervaultRuntimeData,
) -> list[PowervaultEntity]:
    """Build per-string or per-module detailed battery sensors."""
    sensors: list[PowervaultEntity] = []
    coordinator = powervault_data["coordinator"]
    assert coordinator is not None

    for child_key, metrics in coordinator.data.detailed_battery.items():
        for metric_key in metrics:
            sensors.append(
                PowervaultDetailedBatterySensor(powervault_data, child_key, metric_key)
            )
    return sensors


def _build_battery_group_summary_sensors(
    powervault_data: PowervaultRuntimeData,
) -> list[PowervaultEntity]:
    """Build derived voltage summary sensors for each battery group."""
    sensors: list[PowervaultEntity] = []
    coordinator = powervault_data["coordinator"]
    assert coordinator is not None

    for child_key in coordinator.data.detailed_battery:
        if _group_voltage_summary(coordinator.data.detailed_battery[child_key]) is None:
            continue

        for summary_key, summary_name in BATTERY_GROUP_SUMMARY_SENSORS:
            sensors.append(
                PowervaultBatteryGroupSummarySensor(
                    powervault_data,
                    child_key,
                    summary_key,
                    summary_name,
                )
            )

    return sensors


def _build_battery_group_aggregate_sensors(
    powervault_data: PowervaultRuntimeData,
) -> list[PowervaultEntity]:
    """Build shared battery-diagnostics aggregate voltage sensors."""
    coordinator = powervault_data["coordinator"]
    assert coordinator is not None

    if _battery_group_voltage_aggregates(coordinator.data.detailed_battery) is None:
        return []

    return [
        PowervaultBatteryGroupAggregateSensor(
            powervault_data, aggregate_key, aggregate_name
        )
        for aggregate_key, aggregate_name in BATTERY_GROUP_AGGREGATE_SENSORS
    ]


def _child_label(child_key: str) -> str:
    """Return the child device label for a detailed battery group."""
    if child_key.startswith("string"):
        return f"Battery String {child_key.removeprefix('string')}"
    if child_key.startswith("pylontechModule"):
        return f"Battery Module {child_key.removeprefix('pylontechModule')}"
    return child_key


def _detailed_metric_name(metric_key: str) -> str:
    """Return a readable entity name suffix for a detailed metric key."""
    lower = metric_key.lower()
    if "cell" not in metric_key:
        return metric_key

    cell_index = metric_key.split("cell", maxsplit=1)[1]
    if cell_index.endswith("Voltage"):
        return f"Cell {cell_index.removesuffix('Voltage')} Voltage"
    if cell_index.endswith("Temperature"):
        return f"Cell {cell_index.removesuffix('Temperature')} Temperature"
    return metric_key if lower else metric_key


def _detailed_metric_unit(metric_key: str) -> str | None:
    """Return the native unit for a detailed metric key."""
    if metric_key.endswith("Voltage"):
        return cast(str, UnitOfElectricPotential.VOLT)
    if metric_key.endswith("Temperature"):
        return cast(str, UnitOfTemperature.CELSIUS)
    return None


def _detailed_metric_device_class(metric_key: str) -> SensorDeviceClass | None:
    """Return the device class for a detailed metric key."""
    if metric_key.endswith("Voltage"):
        return SensorDeviceClass.VOLTAGE
    if metric_key.endswith("Temperature"):
        return SensorDeviceClass.TEMPERATURE
    return None


def _detailed_metric_precision(metric_key: str) -> int | None:
    """Return rounding precision for a detailed metric key."""
    if metric_key.endswith("Voltage"):
        return 3
    if metric_key.endswith("Temperature"):
        return 1
    return None


def _round_value(value: TelemetryValue, precision: int | None) -> TelemetryValue:
    """Round float telemetry values while leaving other values unchanged."""
    if isinstance(value, float) and precision is not None:
        return round(value, precision)
    if isinstance(value, int) and precision == 0:
        return value
    return value


def _group_voltage_summary(
    metrics: dict[str, TelemetryValue],
) -> dict[str, float] | None:
    """Return derived voltage summary values for a battery group."""
    voltage_values = [
        float(value)
        for key, value in metrics.items()
        if key.endswith("Voltage") and isinstance(value, int | float)
    ]

    if not voltage_values:
        return None

    return {
        "total_voltage": round(sum(voltage_values), 3),
        "average_cell_voltage": round(sum(voltage_values) / len(voltage_values), 3),
        "maximum_cell_voltage": round(max(voltage_values), 3),
    }


def _battery_group_voltage_aggregates(
    detailed_battery: dict[str, dict[str, TelemetryValue]],
) -> dict[str, float] | None:
    """Return aggregate total-voltage summaries across all battery groups."""
    total_voltages = [
        summary["total_voltage"]
        for metrics in detailed_battery.values()
        if (summary := _group_voltage_summary(metrics)) is not None
    ]

    if not total_voltages:
        return None

    return {
        "average_total_voltage": round(sum(total_voltages) / len(total_voltages), 3),
        "maximum_total_voltage": round(max(total_voltages), 3),
    }


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


class PowervaultExtraTelemetrySensor(
    PowervaultEntity, SensorEntity
):  # pylint: disable=too-many-instance-attributes
    """Additive local telemetry sensor placed on a child device."""

    def __init__(
        self,
        powervault_data: PowervaultRuntimeData,
        description: PowervaultExtraSensorDescription,
    ) -> None:
        """Initialize an additive local telemetry sensor."""
        super().__init__(powervault_data)
        self.description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{self.base_unique_id}_{description.unique_id_suffix}"
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_entity_category = description.entity_category
        self._attr_device_info = self.get_child_device_info(
            description.child_device_key,
            description.child_device_name,
        )

    @property
    def native_value(self) -> TelemetryValue | None:
        """Return the current telemetry value for this entity."""
        source = getattr(self.data, self.description.source)
        if (value := source.get(self.description.key)) is None:
            return None
        if self.description.absolute_value and isinstance(value, int | float):
            value = abs(value)
        return _round_value(value, self.description.precision)


class PowervaultDetailedBatterySensor(
    PowervaultEntity, SensorEntity
):  # pylint: disable=too-many-instance-attributes
    """Detailed per-string or per-module battery telemetry sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        powervault_data: PowervaultRuntimeData,
        child_key: str,
        metric_key: str,
    ) -> None:
        """Initialize a detailed battery telemetry sensor."""
        super().__init__(powervault_data)
        self.child_key = child_key
        self.metric_key = metric_key
        self.precision = _detailed_metric_precision(metric_key)
        child_label = _child_label(child_key)
        self._attr_name = (
            f"Powervault {child_label} {_detailed_metric_name(metric_key)}"
        )
        self._attr_unique_id = f"{self.base_unique_id}_{child_key}_{metric_key}"
        self._attr_native_unit_of_measurement = _detailed_metric_unit(metric_key)
        self._attr_device_class = _detailed_metric_device_class(metric_key)
        self._attr_device_info = self.get_child_device_info(
            f"battery_{child_key}",
            child_label,
        )

    @property
    def native_value(self) -> TelemetryValue | None:
        """Return the latest detailed battery telemetry value."""
        value = self.data.detailed_battery.get(self.child_key, {}).get(self.metric_key)
        if value is None:
            return None
        return _round_value(value, self.precision)


class PowervaultBatteryGroupSummarySensor(PowervaultEntity, SensorEntity):
    """Derived voltage summary sensor for a battery module or string."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = SensorDeviceClass.VOLTAGE

    def __init__(
        self,
        powervault_data: PowervaultRuntimeData,
        child_key: str,
        summary_key: str,
        summary_name: str,
    ) -> None:
        """Initialize a derived voltage summary sensor."""
        super().__init__(powervault_data)
        self.child_key = child_key
        self.summary_key = summary_key
        child_label = _child_label(child_key)
        self._attr_name = f"Powervault {child_label} {summary_name}"
        self._attr_unique_id = f"{self.base_unique_id}_{child_key}_{summary_key}"
        self._attr_device_info = self.get_child_device_info(
            "battery_diagnostics",
            "Battery Diagnostics",
        )

    @property
    def native_value(self) -> float | None:
        """Return the derived voltage summary value."""
        metrics = self.data.detailed_battery.get(self.child_key, {})
        if (summary := _group_voltage_summary(metrics)) is None:
            return None
        return summary[self.summary_key]


class PowervaultBatteryGroupAggregateSensor(PowervaultEntity, SensorEntity):
    """Shared battery-diagnostics aggregate sensor derived from group voltages."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_device_class = SensorDeviceClass.VOLTAGE

    def __init__(
        self,
        powervault_data: PowervaultRuntimeData,
        aggregate_key: str,
        aggregate_name: str,
    ) -> None:
        """Initialize an aggregate voltage summary sensor."""
        super().__init__(powervault_data)
        self.aggregate_key = aggregate_key
        self._attr_name = f"Powervault {aggregate_name}"
        self._attr_unique_id = f"{self.base_unique_id}_{aggregate_key}"
        self._attr_device_info = self.get_child_device_info(
            "battery_diagnostics",
            "Battery Diagnostics",
        )

    @property
    def native_value(self) -> float | None:
        """Return the shared aggregate voltage summary value."""
        if (
            aggregates := _battery_group_voltage_aggregates(self.data.detailed_battery)
        ) is None:
            return None
        return aggregates[self.aggregate_key]
