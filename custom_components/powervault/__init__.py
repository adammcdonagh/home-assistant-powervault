"""The Powervault integration."""

from __future__ import annotations

import logging
from datetime import datetime as dt
from datetime import timedelta
from zoneinfo import ZoneInfo

import requests
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from powervaultpy import PowerVault
from powervaultpy.powervault import ServerError

from .const import (
    CONF_IP_ADDRESS,
    CONF_MODEL,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MODEL_LEGACY_P3,
    MODEL_UNKNOWN,
    POWERVAULT_COORDINATOR,
    UPDATE_INTERVAL,
)
from .models import PowervaultBaseInfo, PowervaultData, PowervaultRuntimeData

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Powervault from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    if (model := entry.data.get(CONF_MODEL, MODEL_UNKNOWN)) == MODEL_UNKNOWN:
        raise ConfigEntryAuthFailed(
            "Powervault model not configured. Please reconfigure this integration."
        )

    http_session = requests.Session()

    if model == MODEL_LEGACY_P3:
        local_ip = entry.data[CONF_IP_ADDRESS]
        client = PowerVault(local_ip=local_ip)
        unit_id = None
        base_info = await hass.async_add_executor_job(
            _fetch_base_info_legacy, client, local_ip
        )
    else:
        api_key = entry.data["api_key"]
        unit_id = entry.data["unit_id"]
        local_ip = None
        client = PowerVault(api_key)
        base_info = await hass.async_add_executor_job(_fetch_base_info, client, unit_id)

    runtime_data = PowervaultRuntimeData(
        api_changed=False,
        base_info=base_info,
        http_session=http_session,
        coordinator=None,
        api_instance=client,
    )

    manager = PowervaultDataManager(
        hass, client, unit_id, runtime_data, local_ip=local_ip
    )

    if local_ip:
        poll_interval = int(
            entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        )
    else:
        poll_interval = UPDATE_INTERVAL

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Powervault site",
        update_method=manager.async_update_data,
        update_interval=timedelta(seconds=poll_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    runtime_data[POWERVAULT_COORDINATOR] = coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if local_ip:

        async def _options_updated(
            _hass: HomeAssistant, updated_entry: ConfigEntry
        ) -> None:
            new_interval = int(
                updated_entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            )
            coordinator.update_interval = timedelta(seconds=new_interval)

        entry.async_on_unload(entry.add_update_listener(_options_updated))

    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry to current version."""
    _LOGGER.debug(
        "Migrating Powervault config entry from version %s", config_entry.version
    )

    if config_entry.version == 1:
        # v1 entries predate the model field. We cannot determine from stored data
        # alone whether this is a P3 or a newer unit, so we stamp "unknown".
        # async_setup_entry will raise ConfigEntryAuthFailed which triggers a reauth
        # flow that asks the user to identify their model and (for P3) enter their IP.
        hass.config_entries.async_update_entry(
            config_entry,
            data={**config_entry.data, CONF_MODEL: MODEL_UNKNOWN},
            version=2,
        )
        _LOGGER.info(
            "Migrated Powervault config entry to version 2; user must confirm model"
        )
        return True

    _LOGGER.error(
        "Cannot migrate Powervault config entry from version %s", config_entry.version
    )
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:  # pylint: disable=consider-using-assignment-expr
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok  # type: ignore[no-any-return]


def _fetch_base_info(client: PowerVault, unit_id: str) -> PowervaultBaseInfo:
    return _call_base_info(client, unit_id)


def _fetch_base_info_legacy(client: PowerVault, _local_ip: str) -> PowervaultBaseInfo:
    uid = client.get_unit_id()
    return PowervaultBaseInfo(id=uid, model="Powervault P3", eprom_id="")


def _call_base_info(client: PowerVault, unit_id: str) -> PowervaultBaseInfo:
    """Return PowervaultBaseInfo for the device."""
    unit_data = client.get_unit(unit_id)
    return PowervaultBaseInfo(
        id=unit_data["id"], model=unit_data["model"], eprom_id=unit_data["epromId"]
    )


def get_kwh(data: dict) -> dict:
    """Convert the W reading to kWh over the 5 minute period.

    :param data: The data to convert
    :return: The converted data
    """
    # List of attributes to retrieve from data dict
    attributes = [
        "batteryInputFromGrid",
        "batteryInputFromSolar",
        "batteryOutputConsumedByHome",
        "batteryOutputExported",
        "homeConsumed",
        "gridConsumedByHome",
        "solarConsumedByHome",
        "solarExported",
        "solarGenerated",
    ]
    # For each attribute, loop through the data dict and convert the W reading to kWh over the 5 minute period
    totals: dict[str, float] = {}
    for row in data:
        for attribute in attributes:
            if attribute in row:
                if attribute not in totals or not totals[attribute]:
                    totals[attribute] = 0
                value = row[attribute]
                if value := row[attribute]:
                    totals[attribute] += round(value / 1000 * (5 / 60), 2)

    return totals


class PowervaultDataManager:  # pylint: disable=too-few-public-methods
    """Class to manager powervault data."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        hass: HomeAssistant,
        client: PowerVault,
        unit_id: str | None,
        runtime_data: PowervaultRuntimeData,
        local_ip: str | None = None,
    ) -> None:
        """Init the data manager."""
        self.hass = hass
        self.unit_id = unit_id
        self.local_ip = local_ip
        self.runtime_data = runtime_data
        self.client = client

    async def async_update_data(self) -> PowervaultData:
        """Fetch data from API endpoint."""
        # Check if we had an error before
        _LOGGER.debug("Checking if update failed")

        return await self.hass.async_add_executor_job(self._update_data)  # type: ignore[no-any-return]

    def _update_data(self) -> PowervaultData:
        """Fetch data from API endpoint."""
        _LOGGER.debug("Updating data")
        for _ in range(2):
            try:
                data = _fetch_powervault_data(
                    self.client, self.unit_id, local_ip=self.local_ip
                )
            except ServerError as err:
                raise UpdateFailed("Unable to fetch data from powervault") from err

            return data
        raise RuntimeError("unreachable")


def _fetch_powervault_data(  # pylint: disable=too-many-branches
    client: PowerVault, unit_id: str | None, local_ip: str | None = None
) -> PowervaultData:
    """Process and update powervault data."""
    if local_ip:
        return _fetch_powervault_data_legacy(client)
    return _fetch_powervault_data_cloud(client, unit_id)  # type: ignore[arg-type]


def _fetch_powervault_data_legacy(  # pylint: disable=too-many-locals,too-many-statements
    client: PowerVault,
) -> PowervaultData:
    """Fetch data from a legacy P3 Powervault unit via the local REST API."""
    data = client.get_data(None)

    _LOGGER.debug(f"Local data: {data}")

    if not data or len(data) == 0:
        raise ServerError(
            "Failed to get data from Powervault local API. Empty response."
        )

    # Local API returns a list of {measurement, value, ...} objects — flatten to a dict.
    # Entries with None values are excluded so .get() fallbacks of 0 apply cleanly.
    telemetry = {
        item["measurement"]: item["value"]
        for item in data
        if item.get("value") is not None
    }

    _LOGGER.debug(f"Telemetry: {telemetry}")

    if "socUsable" not in telemetry:
        raise ServerError(
            "Failed to get data from Powervault local API. Missing expected measurements."
        )

    # Fetch today's historical chart data to derive energy totals.
    # Midnight..end-of-day in local time, converted to UTC-aware datetimes.

    local_tz = ZoneInfo("Europe/London")
    now_local = dt.now(local_tz)
    today_midnight = dt(
        now_local.year, now_local.month, now_local.day, 0, 0, 0, tzinfo=local_tz
    )
    today_end = dt(
        now_local.year, now_local.month, now_local.day, 23, 59, 59, tzinfo=local_tz
    )
    _LOGGER.debug(f"Today midnight/end: {today_midnight}/{today_end}")

    chart_totals: dict[str, float] = {}
    try:
        chart_data = client.get_chart_data(today_midnight, today_end)
        # Debnug log the chart data, but only the first 5 entries
        _LOGGER.debug(f"Chart data: {chart_data[:5]}")
        # chart_data is a list of lists — each inner list is a group of
        # {measurement, value, timestamp, ...} objects sharing the same timestamp.
        # For each 30-second sample, extract the three power measurements then
        # compute per-sample energy flows (kWh = W × 30s / 3600s / 1000).
        interval_wh = 30 / 3600  # 30-second sample interval → Wh per sample

        acc: dict[str, float] = {
            "batteryInputFromGrid": 0.0,
            "batteryInputFromSolar": 0.0,
            "batteryOutputConsumedByHome": 0.0,
            "batteryOutputExported": 0.0,
            "solarConsumedByHome": 0.0,
            "solarExported": 0.0,
            "solarGenerated": 0.0,
            "gridConsumedByHome": 0.0,
            "homeConsumed": 0.0,
        }

        # Carry the last known value for each power channel so that groups
        # which only contain a subset of measurements still contribute correctly.
        last_grid_w: float = 0.0
        last_battery_w: float = 0.0
        last_solar_w: float = 0.0

        for timestamp_group in chart_data:
            measurements: dict[str, float] = {
                item["measurement"]: item["value"]
                for item in timestamp_group
                if item.get("measurement") is not None and item.get("value") is not None
            }

            last_grid_w = measurements.get("gridPower", last_grid_w)
            last_battery_w = measurements.get("batteryPower", last_battery_w)
            last_solar_w = measurements.get("aux1Power", last_solar_w)

            grid_w = last_grid_w
            battery_w = last_battery_w
            solar_w = last_solar_w

            # Signed convention:
            # gridPower:    positive = importing, negative = exporting
            # batteryPower: negative = discharging, positive = charging
            # aux1Power:    negative = generating, positive = aux load
            grid_import_w = max(grid_w, 0.0)
            grid_export_w = max(-grid_w, 0.0)
            battery_discharge_w = max(-battery_w, 0.0)
            battery_charge_w = max(battery_w, 0.0)
            solar_gen_w = max(-solar_w, 0.0)

            # Solar allocation (solar-first priority):
            # Solar covers home load first, then battery charge, then grid export.
            solar_remaining = solar_gen_w
            home_from_solar = min(
                solar_remaining,
                max(
                    0.0,
                    solar_gen_w
                    + battery_discharge_w
                    + grid_import_w
                    - battery_charge_w,
                ),
            )
            solar_remaining -= home_from_solar
            battery_from_solar = min(solar_remaining, battery_charge_w)
            solar_remaining -= battery_from_solar
            solar_exported_w = min(solar_remaining, grid_export_w)

            # Battery charge source: remaining charge after solar covered
            battery_from_grid = max(0.0, battery_charge_w - battery_from_solar)

            # Battery discharge allocation: home first, grid export second
            battery_to_home = min(
                battery_discharge_w,
                max(
                    0.0,
                    battery_discharge_w
                    + solar_gen_w
                    + grid_import_w
                    - battery_charge_w
                    - grid_export_w,
                ),
            )
            battery_exported_w = max(0.0, battery_discharge_w - battery_to_home)

            # Home consumption
            home_w = (
                grid_import_w
                + battery_discharge_w
                + solar_gen_w
                - battery_charge_w
                - grid_export_w
            )

            acc["batteryInputFromGrid"] += battery_from_grid * interval_wh
            acc["batteryInputFromSolar"] += battery_from_solar * interval_wh
            acc["batteryOutputConsumedByHome"] += battery_to_home * interval_wh
            acc["batteryOutputExported"] += battery_exported_w * interval_wh
            acc["solarConsumedByHome"] += home_from_solar * interval_wh
            acc["solarExported"] += solar_exported_w * interval_wh
            acc["solarGenerated"] += solar_gen_w * interval_wh
            acc["gridConsumedByHome"] += (
                grid_import_w * interval_wh
            )  # includes battery charging from grid
            acc["homeConsumed"] += max(home_w, 0.0) * interval_wh

        chart_totals = {k: round(v, 3) for k, v in acc.items()}
        _LOGGER.debug(f"Chart totals: {chart_totals}")

        # Get the min and max times for the chart data and convert them to human-readable strings
        chart_min_time = chart_data[0][0]["timestamp"]
        chart_max_time = chart_data[-1][0]["timestamp"]
        chart_min_time = dt.fromtimestamp(chart_min_time, local_tz)
        chart_max_time = dt.fromtimestamp(chart_max_time, local_tz)
        _LOGGER.debug("Chart min/max times: %s/%s", chart_min_time, chart_max_time)

    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning(f"Failed to fetch chart data for totals: {err}")

    battery_state = "UNKNOWN"
    try:
        battery_state = client.get_battery_state(None)
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.error(f"Failed to get battery state: {err}")
        _LOGGER.error(
            "Missing battery state indicates there's no schedule available and no overrides in place. Setting value to UNKNOWN"
        )

    # Sign convention: positive gridPower = importing; negative batteryPower = discharging;
    # aux1Power (solar) is negative when generating.
    grid_power = telemetry.get("gridPower", 0)
    battery_power = telemetry.get("batteryPower", 0)
    solar_power = telemetry.get("aux1Power", 0)

    # Derived instant values (in W)
    instant_solar_gen_w = max(-solar_power, 0.0)
    instant_battery_discharge_w = max(-battery_power, 0.0)
    instant_battery_charge_w = max(battery_power, 0.0)
    instant_grid_import_w = max(grid_power, 0.0)
    instant_grid_export_w = max(-grid_power, 0.0)

    # home demand = all sources flowing into the home
    instant_demand_w = max(
        instant_grid_import_w
        + instant_battery_discharge_w
        + instant_solar_gen_w
        - instant_battery_charge_w,
        0.0,
    )

    # Solar-first instant breakdown (mirrors the chart allocation logic)
    sol_rem = instant_solar_gen_w
    inst_solar_to_home = min(sol_rem, instant_demand_w)
    sol_rem -= inst_solar_to_home
    inst_solar_to_battery = min(sol_rem, instant_battery_charge_w)
    sol_rem -= inst_solar_to_battery
    inst_solar_exported = min(sol_rem, instant_grid_export_w)

    inst_battery_from_grid = max(0.0, instant_battery_charge_w - inst_solar_to_battery)
    inst_battery_to_home = min(
        instant_battery_discharge_w,
        max(0.0, instant_demand_w - inst_solar_to_home),
    )
    inst_battery_exported = max(0.0, instant_battery_discharge_w - inst_battery_to_home)

    # All instant fields are stored in mW — sensor.py divides by 1000 to display W.
    milli = 1000

    return PowervaultData(
        charge=telemetry.get("socUsable", 0),
        batteryInputFromGrid=inst_battery_from_grid * milli,
        batteryInputFromSolar=inst_solar_to_battery * milli,
        batteryOutputConsumedByHome=inst_battery_to_home * milli,
        batteryOutputExported=inst_battery_exported * milli,
        homeConsumed=instant_demand_w * milli,
        gridConsumedByHome=instant_grid_import_w * milli,
        solarConsumedByHome=inst_solar_to_home * milli,
        solarExported=inst_solar_exported * milli,
        instant_battery=battery_power * milli * -1,
        instant_demand=instant_demand_w * milli * -1,
        instant_grid=grid_power * milli,
        solarGenerated=instant_solar_gen_w * milli,
        solarConsumption=inst_solar_to_home * milli,
        instant_solar=instant_solar_gen_w * milli,
        battery_state=battery_state,
        totals={
            "batteryInputFromGrid": chart_totals.get("batteryInputFromGrid", 0),
            "batteryInputFromSolar": chart_totals.get("batteryInputFromSolar", 0),
            "batteryOutputConsumedByHome": chart_totals.get(
                "batteryOutputConsumedByHome", 0
            ),
            "batteryOutputExported": chart_totals.get("batteryOutputExported", 0),
            "gridConsumedByHome": chart_totals.get("gridConsumedByHome", 0),
            "solarGenerated": chart_totals.get("solarGenerated", 0),
            "solarConsumedByHome": chart_totals.get("solarConsumedByHome", 0),
            "solarExported": chart_totals.get("solarExported", 0),
            "homeConsumed": chart_totals.get("homeConsumed", 0),
        },
    )


def _fetch_powervault_data_cloud(  # pylint: disable=too-many-branches
    client: PowerVault, unit_id: str
) -> PowervaultData:
    """Process and update powervault data."""
    data = client.get_data(unit_id)

    _LOGGER.info(f"Data: {data}")

    # Check the 0 index data keys, for any values that are None
    need_to_get_past_hour = False
    for key in data[0]:
        if data[0][key] is None:
            need_to_get_past_hour = True
            break

    if need_to_get_past_hour:
        _LOGGER.info("Getting past-hour because at least one value is None")
        past_hour_data = client.get_data(unit_id, period="past-hour")
        _LOGGER.info(f"Data: {data}")

        # Loop through keys of data[0] and replace any None values with the last value in the past hour,
        # going back 1 index at a time until we find a value that is not None
        for key in data[0]:
            # Ignore the "time" key
            if key == "time":
                continue
            if data[0][key] is None:
                current_index = len(past_hour_data) - 1
                while current_index >= 0:
                    if (
                        current_value := past_hour_data[current_index][key]
                    ) is not None:
                        data[0][key] = current_value
                        _LOGGER.info(
                            f"Replacing value of {key} to populated_entry from"
                            f" {past_hour_data[current_index]['time']} with value"
                            f" {current_value}"
                        )
                        break
                    current_index -= 1

    # Check that there is some data
    if not data or len(data) == 0 or "instant_soc" not in data[0]:
        raise ServerError(
            "Failed to get data from Powervault API. Missing data from API call."
        )

    _LOGGER.info(f"Returning: {data}")

    totals = client.get_data(unit_id, period="today")

    if not totals or len(totals) == 0 or "instant_soc" not in totals[0]:
        raise ServerError(
            "Failed to get totals data from Powervault API. Missing data from API call."
        )

    # Check for None values in any of the total data. Use instant_battery as a test
    for row in totals:
        # Remove anything that is None
        if "instant_battery" not in row or row["instant_battery"] is None:
            totals.remove(row)

    totals = get_kwh(totals)

    _LOGGER.info(f"Totals: {totals}")

    battery_state = "UNKNOWN"
    try:
        battery_state = client.get_battery_state(unit_id)
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.error(f"Failed to get battery state: {err}")
        _LOGGER.error(
            "Missing battery state indicates there's no schedule available and no overrides in place. Setting value to UNKNOWN"
        )

    return PowervaultData(
        charge=data[0]["instant_soc"],
        batteryInputFromGrid=data[0]["batteryInputFromGrid"],
        batteryInputFromSolar=data[0]["batteryInputFromSolar"],
        batteryOutputConsumedByHome=data[0]["batteryOutputConsumedByHome"],
        batteryOutputExported=data[0]["batteryOutputExported"],
        homeConsumed=data[0]["homeConsumed"],
        gridConsumedByHome=data[0]["gridConsumedByHome"],
        solarConsumedByHome=data[0]["solarConsumedByHome"],
        solarExported=data[0]["solarExported"],
        instant_battery=data[0]["instant_battery"],
        instant_demand=data[0]["instant_demand"],
        instant_grid=data[0]["instant_grid"],
        solarGenerated=data[0]["solarGenerated"],
        solarConsumption=data[0]["solarConsumption"],
        instant_solar=(
            data[0]["instant_solar"] if data[0]["instant_solar"] > 10000 else 0
        ),
        battery_state=battery_state,
        totals=totals,
    )
