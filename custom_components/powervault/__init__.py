"""The Powervault integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import requests
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from powervaultpy import PowerVault
from powervaultpy.powervault import ServerError

from .const import DOMAIN, POWERVAULT_COORDINATOR, UPDATE_INTERVAL
from .models import PowervaultBaseInfo, PowervaultData, PowervaultRuntimeData

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Powervault from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    api_key = entry.data["api_key"]
    unit_id = entry.data["unit_id"]
    client = PowerVault(api_key)

    http_session = requests.Session()

    base_info = await hass.async_add_executor_job(_fetch_base_info, client, unit_id)

    runtime_data = PowervaultRuntimeData(
        api_changed=False,
        base_info=base_info,
        http_session=http_session,
        coordinator=None,
        api_instance=client,
    )

    manager = PowervaultDataManager(hass, client, unit_id, runtime_data)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Powervault site",
        update_method=manager.async_update_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    runtime_data[POWERVAULT_COORDINATOR] = coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:  # pylint: disable=consider-using-assignment-expr
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok  # type: ignore[no-any-return]


def _fetch_base_info(client: PowerVault, unit_id: str) -> PowervaultBaseInfo:
    return _call_base_info(client, unit_id)


def _call_base_info(client: PowerVault, unit_id: str) -> PowervaultBaseInfo:
    """Return PowervaultBaseInfo for the device."""
    unit_data = client.get_unit(unit_id)
    return PowervaultBaseInfo(
        id=unit_data["id"], model=unit_data["model"], eprom_id=unit_data["epromId"]
    )

def get_kwh(data: dict) -> dict:
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
    # For each attribute, loop through the data dict and conver the W reading to kWh over the 5 minute period
    totals = {}
    for row in data:
        for attribute in attributes:
            if attribute in row:
                if attribute not in totals or not totals[attribute]:
                    totals[attribute] = 0
                value = row[attribute]
                if value:
                    totals[attribute] += round(value / 1000 * (5/60), 2)

    return totals


class PowervaultDataManager:  # pylint: disable=too-few-public-methods
    """Class to manager powervault data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PowerVault,
        unit_id: str,
        runtime_data: PowervaultRuntimeData,
    ) -> None:
        """Init the data manager."""
        self.hass = hass
        self.unit_id = unit_id
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
                data = _fetch_powervault_data(self.client, self.unit_id)
            except ServerError as err:
                raise UpdateFailed("Unable to fetch data from powervault") from err

            return data
        raise RuntimeError("unreachable")


def _fetch_powervault_data(client: PowerVault, unit_id: str) -> PowervaultData:
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
        _LOGGER.info(f"Getting past-hour because at least one value is None")
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
                    current_value = past_hour_data[current_index][key]
                    if current_value is not None:
                        data[0][key] = current_value
                        _LOGGER.info(f"Replacing value of {key} to populated_entry from {past_hour_data[current_index]['time']} with value {current_value}")
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

    battery_state = client.get_battery_state(unit_id)

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
        instant_solar=data[0]["instant_solar"]
        if data[0]["instant_solar"] > 10000
        else 0,
        battery_state=battery_state,
        totals=totals,
    )
