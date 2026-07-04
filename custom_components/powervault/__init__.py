"""The Powervault integration."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import date
from datetime import datetime as dt
from datetime import timedelta, timezone, tzinfo
from typing import cast

import requests
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from powervaultpy import PowerVault
from powervaultpy.powervault import ServerError

from .const import (
    CONF_IP_ADDRESS,
    CONF_MODEL,
    CONF_PLATFORM,
    CONF_POLL_INTERVAL,
    CONF_USE_API_HISTORY,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    LEGACY_PLATFORM_P3,
    LEGACY_PLATFORM_P3X,
    LEGACY_PLATFORMS,
    MODEL_LEGACY_P3,
    MODEL_UNKNOWN,
    POWERVAULT_COORDINATOR,
    POWERVAULT_MANAGER,
    UPDATE_INTERVAL,
)
from .models import (
    PowervaultBaseInfo,
    PowervaultData,
    PowervaultRuntimeData,
    TelemetryValue,
)

_LOGGER = logging.getLogger(__name__)
P3_STRING_CELL_RE = re.compile(r"^(string\d+)cell\d+(Voltage|Temperature)$")
P3_PACK_TEMPERATURE_RE = re.compile(r"^pack\d+Temperature$")
P3_BACKPLANE_TEMPERATURE_RE = re.compile(r"^backplane\d+Temperature$")
P3_STRING_VOLTAGE_RE = re.compile(r"^string\d+cell\d+Voltage$")
P3_STRING_TEMPERATURE_RE = re.compile(r"^string\d+cell\d+Temperature$")
P3X_MODULE_CELL_RE = re.compile(r"^(pylontechModule\d+)cell\d+(Voltage|Temperature)$")
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
]


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
        local_platform = await _async_ensure_legacy_platform(hass, entry, client)
        base_info = await hass.async_add_executor_job(
            _fetch_base_info_legacy, client, local_platform
        )
    else:
        api_key = entry.data["api_key"]
        unit_id = entry.data["unit_id"]
        local_ip = None
        local_platform = None
        client = PowerVault(api_key)
        base_info = await hass.async_add_executor_job(_fetch_base_info, client, unit_id)

    runtime_data = PowervaultRuntimeData(
        api_changed=False,
        base_info=base_info,
        http_session=http_session,
        coordinator=None,
        api_instance=client,
        manager=None,  # type: ignore[typeddict-item]
    )

    manager = PowervaultDataManager(
        hass=hass,
        client=client,
        unit_id=unit_id,
        runtime_data=runtime_data,
        local_ip=local_ip,
        local_platform=local_platform,
        config_entry=entry,
    )
    runtime_data[POWERVAULT_MANAGER] = manager

    if local_ip:
        await manager.async_initialize()
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
            version=3,
        )
        _LOGGER.info(
            "Migrated Powervault config entry to version 3; user must confirm model"
        )
        return True

    if config_entry.version == 2:
        updated_data = dict(config_entry.data)

        if (
            updated_data.get(CONF_MODEL) == MODEL_LEGACY_P3
            and updated_data.get(CONF_PLATFORM) not in LEGACY_PLATFORMS
            and (local_ip := updated_data.get(CONF_IP_ADDRESS))
        ):
            client = PowerVault(local_ip=local_ip)
            try:
                updated_data[CONF_PLATFORM] = await hass.async_add_executor_job(
                    _fetch_legacy_platform, client
                )
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.warning(
                    "Unable to determine stored Powervault local platform during migration: %s",
                    err,
                )

        hass.config_entries.async_update_entry(
            config_entry,
            data=updated_data,
            version=3,
        )
        _LOGGER.info("Migrated Powervault config entry to version 3")
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


def _fetch_base_info_legacy(
    client: PowerVault, local_platform: str
) -> PowervaultBaseInfo:
    uid = client.get_unit_id()
    return PowervaultBaseInfo(
        id=uid,
        model=f"Powervault {local_platform.upper()}",
        eprom_id="",
    )


def _fetch_legacy_platform(client: PowerVault) -> str:
    """Return a normalized stored platform value for a legacy local unit."""
    return _normalize_legacy_platform(client.get_platform())


def _normalize_legacy_platform(platform: str | None) -> str:
    """Validate and normalize a local platform identifier."""
    if platform is None:
        raise ValueError("Powervault local platform is missing")

    if (normalized := platform.strip().lower()) not in LEGACY_PLATFORMS:
        raise ValueError(f"Unsupported Powervault local platform: {platform}")

    return normalized


async def _async_ensure_legacy_platform(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: PowerVault,
) -> str:
    """Return the stored legacy platform, persisting it once if missing."""
    stored_platform = entry.data.get(CONF_PLATFORM)
    if isinstance(stored_platform, str) and stored_platform in LEGACY_PLATFORMS:
        return stored_platform

    detected_platform = cast(
        str,
        await hass.async_add_executor_job(_fetch_legacy_platform, client),
    )
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_PLATFORM: detected_platform},
    )
    return detected_platform


def _call_base_info(client: PowerVault, unit_id: str) -> PowervaultBaseInfo:
    """Return PowervaultBaseInfo for the device."""
    unit_data = client.get_unit(unit_id)
    return PowervaultBaseInfo(
        id=cast(str, unit_data["id"]),
        model=cast(str, unit_data["model"]),
        eprom_id=cast(str, unit_data["epromId"]),
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


def _compute_sample_flows(
    grid_w: float, battery_w: float, solar_w: float, interval_wh: float
) -> dict[str, float]:
    """Return energy flow deltas (Wh) for one sample interval."""
    grid_import_w = max(grid_w, 0.0)
    grid_export_w = max(-grid_w, 0.0)
    battery_discharge_w = max(-battery_w, 0.0)
    battery_charge_w = max(battery_w, 0.0)
    solar_gen_w = max(-solar_w, 0.0)

    solar_rem = solar_gen_w
    home_from_solar = min(
        solar_rem,
        max(0.0, solar_gen_w + battery_discharge_w + grid_import_w - battery_charge_w),
    )
    solar_rem -= home_from_solar
    battery_from_solar = min(solar_rem, battery_charge_w)
    solar_rem -= battery_from_solar
    solar_exported_w = min(solar_rem, grid_export_w)

    battery_from_grid = max(0.0, battery_charge_w - battery_from_solar)
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
    home_w = (
        grid_import_w
        + battery_discharge_w
        + solar_gen_w
        - battery_charge_w
        - grid_export_w
    )

    return {
        "batteryInputFromGrid": battery_from_grid * interval_wh,
        "batteryInputFromSolar": battery_from_solar * interval_wh,
        "batteryOutputConsumedByHome": battery_to_home * interval_wh,
        "batteryOutputExported": max(0.0, battery_discharge_w - battery_to_home)
        * interval_wh,
        "solarConsumedByHome": home_from_solar * interval_wh,
        "solarExported": solar_exported_w * interval_wh,
        "solarGenerated": solar_gen_w * interval_wh,
        "gridConsumedByHome": grid_import_w * interval_wh,
        "homeConsumed": max(home_w, 0.0) * interval_wh,
    }


def _get_local_timezone(hass: HomeAssistant) -> tzinfo:
    """Return the configured Home Assistant timezone, falling back safely."""
    if tz_name := hass.config.time_zone:
        if time_zone := dt_util.get_time_zone(tz_name):
            return cast(tzinfo, time_zone)

    if (default_time_zone := dt_util.DEFAULT_TIME_ZONE) is not None:
        return cast(tzinfo, default_time_zone)

    return timezone.utc


def _parse_chart_timestamp(value: object) -> dt | None:
    """Parse a chart data timestamp into a timezone-aware UTC datetime."""
    if isinstance(value, int | float):
        timestamp_value = value / 1000 if value > 1_000_000_000_000 else value
        return dt.fromtimestamp(timestamp_value, tz=timezone.utc)

    if isinstance(value, str):
        try:
            parsed = dt.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    return None


def _normalize_chart_samples(chart_data: object) -> list[dict[str, object]]:
    """Normalize chart data into a flat list of per-sample dicts."""
    if not isinstance(chart_data, list):
        return []

    samples: list[dict[str, object]] = []

    for entry in chart_data:
        if isinstance(entry, dict):
            samples.append(dict(entry))
            continue

        if not isinstance(entry, list):
            continue

        sample: dict[str, object] = {}
        for item in entry:
            if not isinstance(item, dict):
                continue

            if "timestamp" not in sample and item.get("timestamp") is not None:
                sample["timestamp"] = item["timestamp"]
            if "created_at" not in sample and item.get("created_at") is not None:
                sample["created_at"] = item["created_at"]

            measurement = item.get("measurement")
            value = item.get("value")
            if measurement is not None and value is not None:
                sample[str(measurement)] = value

        if sample:
            samples.append(sample)

    return samples


def _filter_current_day_chart_samples(
    chart_data: object, local_tz: tzinfo, today: date
) -> tuple[list[dict[str, object]], int]:
    """Return only samples that belong to the current local date."""
    current_day_samples: list[dict[str, object]] = []
    skipped_samples = 0

    for sample in _normalize_chart_samples(chart_data):
        parsed_timestamp = _parse_chart_timestamp(
            sample.get("timestamp") or sample.get("created_at")
        )
        if parsed_timestamp is None:
            skipped_samples += 1
            continue

        if parsed_timestamp.astimezone(local_tz).date() != today:
            skipped_samples += 1
            continue

        current_day_samples.append(sample)

    return current_day_samples, skipped_samples


def _try_fetch_chart_totals(  # pylint: disable=too-many-locals
    client: PowerVault, local_tz: tzinfo
) -> dict[str, float] | None:
    """Fetch today's chart data and derive energy totals.

    Returns a dict keyed by the standard total keys (values in Wh) on success,
    or None if the fetch fails or the data appears incomplete.
    """
    now_local = dt.now(local_tz)
    today = now_local.date()
    today_midnight = dt(
        now_local.year, now_local.month, now_local.day, 0, 0, 0, tzinfo=local_tz
    )
    today_end = dt(
        now_local.year, now_local.month, now_local.day, 23, 59, 59, tzinfo=local_tz
    )

    try:
        chart_data = client.get_chart_data(today_midnight, today_end)
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.debug("Chart data fetch failed: %s", err)
        return None

    if not chart_data:
        return None

    valid_chart_data, skipped_samples = _filter_current_day_chart_samples(
        chart_data, local_tz, today
    )

    if not valid_chart_data:
        if skipped_samples:
            _LOGGER.debug(
                "Discarding chart totals because no samples matched local date %s",
                today,
            )
        return None

    if skipped_samples:
        _LOGGER.debug(
            "Skipped %s chart samples outside local date %s",
            skipped_samples,
            today,
        )

    interval_wh = 30 / 3600  # 30-second samples
    acc: dict[str, float] = dict.fromkeys(
        (
            "batteryInputFromGrid",
            "batteryInputFromSolar",
            "batteryOutputConsumedByHome",
            "batteryOutputExported",
            "solarConsumedByHome",
            "solarExported",
            "solarGenerated",
            "gridConsumedByHome",
            "homeConsumed",
        ),
        0.0,
    )

    last_grid_w: float = 0.0
    last_battery_w: float = 0.0
    last_solar_w: float = 0.0

    for sample in valid_chart_data:
        grid_power = sample.get("gridPower")
        battery_power = sample.get("batteryPower")
        solar_power = sample.get("aux1Power")

        if isinstance(grid_power, int | float):
            last_grid_w = float(grid_power)
        if isinstance(battery_power, int | float):
            last_battery_w = float(battery_power)
        if isinstance(solar_power, int | float):
            last_solar_w = float(solar_power)

        for key, delta in _compute_sample_flows(
            last_grid_w, last_battery_w, last_solar_w, interval_wh
        ).items():
            acc[key] += delta

    return {k: round(v, 3) for k, v in acc.items()}


class PowervaultDataManager:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Class to manager powervault data."""

    _TOTAL_KEYS = (
        "batteryInputFromGrid",
        "batteryInputFromSolar",
        "batteryOutputConsumedByHome",
        "batteryOutputExported",
        "homeConsumed",
        "gridConsumedByHome",
        "solarConsumedByHome",
        "solarExported",
        "solarGenerated",
    )

    def __init__(  # pylint: disable=too-many-arguments
        self,
        hass: HomeAssistant,
        client: PowerVault,
        unit_id: str | None,
        runtime_data: PowervaultRuntimeData,
        local_ip: str | None = None,
        local_platform: str | None = None,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        """Init the data manager."""
        self.hass = hass
        self.unit_id = unit_id
        self.local_ip = local_ip
        self.local_platform = local_platform
        self.runtime_data = runtime_data
        self.client = client
        self.config_entry = config_entry
        self._local_tz = _get_local_timezone(hass)
        # Incremental energy accumulator for local P3 path.
        self._acc: dict[str, float] = dict.fromkeys(self._TOTAL_KEYS, 0.0)
        self._last_poll_time: dt | None = None
        self._acc_date: date | None = None
        # Persistent storage for the accumulator.
        store_key = (
            f"{DOMAIN}_{entry.entry_id}_accumulator"
            if (entry := config_entry)
            else None
        )
        self._store: Store | None = Store(hass, 1, store_key) if store_key else None

    async def async_initialize(self) -> None:
        """Load persisted accumulator state from storage."""
        if not self._store:
            return
        if not (stored := await self._store.async_load()):
            return
        if not (stored_date_str := stored.get("date")):
            return
        stored_date = date.fromisoformat(stored_date_str)
        today = dt.now(self._local_tz).date()
        if stored_date != today:
            _LOGGER.debug("Persisted accumulator is from a previous day — discarding")
            await self._store.async_remove()
            return
        acc = stored.get("acc", {})
        for key in self._TOTAL_KEYS:
            if key in acc:
                self._acc[key] = float(acc[key])
        self._acc_date = stored_date
        _LOGGER.debug("Restored accumulator from storage: %s", self._acc)

    async def async_update_data(self) -> PowervaultData:
        """Fetch data from API endpoint."""
        # Check if we had an error before
        _LOGGER.debug("Checking if update failed")

        data = await self.hass.async_add_executor_job(self._update_data)
        if self.local_ip:
            await self._async_save_accumulator()
        return data  # type: ignore[no-any-return]

    async def _async_save_accumulator(self) -> None:
        """Persist the current accumulator to storage."""
        if self._store and self._acc_date:
            await self._store.async_save(
                {"date": self._acc_date.isoformat(), "acc": dict(self._acc)}
            )

    async def async_reset_cached_totals(self) -> None:
        """Clear cached daily totals and persisted accumulator state."""
        self._acc = dict.fromkeys(self._TOTAL_KEYS, 0.0)
        self._last_poll_time = None
        self._acc_date = dt.now(self._local_tz).date()
        if self._store:
            await self._store.async_remove()

    def _update_data(self) -> PowervaultData:
        """Fetch data from API endpoint."""
        _LOGGER.debug("Updating data")
        for _ in range(2):
            try:
                data = _fetch_powervault_data(
                    self.client,
                    self.unit_id,
                    local_ip=self.local_ip,
                    local_platform=self.local_platform,
                )
            except ServerError as err:
                raise UpdateFailed("Unable to fetch data from powervault") from err

            if self.local_ip:
                use_history = (
                    self.config_entry.options.get(CONF_USE_API_HISTORY, True)
                    if self.config_entry
                    else True
                )
                api_totals = (
                    _try_fetch_chart_totals(self.client, self._local_tz)
                    if use_history
                    else None
                )
                data = self._accumulate(data, api_totals=api_totals)

            return data
        raise RuntimeError("unreachable")

    def _accumulate(
        self,
        data: PowervaultData,
        api_totals: dict[str, float] | None = None,
    ) -> PowervaultData:
        """Accumulate instantaneous power readings into daily energy totals (Wh).

        Called only for the local P3 path. Each poll:
        1. Adds ΔWh (from instantaneous values) to the running accumulator.
        2. If the API chart totals are available and >= the accumulator for a
           given key, the API value is used instead (it is more accurate, being
           derived from 30-second resolution history). If the API value has
           dropped below the accumulator — indicating a mid-day history reset —
           the accumulator is kept, so the total never goes backwards.
        """
        now = dt.now(self._local_tz)
        today = now.date()

        # Reset at midnight.
        if self._acc_date is not None and self._acc_date != today:
            _LOGGER.debug("New day detected — resetting energy accumulator")
            self._acc = dict.fromkeys(self._TOTAL_KEYS, 0.0)
        self._acc_date = today

        if self._last_poll_time is not None:
            # Only accumulate if the gap is ≤5 minutes. Larger gaps indicate a
            # restart or extended outage — skip to avoid inflating totals.
            if (
                elapsed_hours := (now - self._last_poll_time).total_seconds() / 3600
            ) <= 5 / 60:
                for key in self._TOTAL_KEYS:
                    mw_value = getattr(data, key, None)
                    if mw_value is not None and mw_value >= 0:
                        # PowervaultData stores instant values in mW.
                        # mW / 1000 = W; W * hours = Wh.
                        # sensor.py divides totals by 1000 to display kWh.
                        self._acc[key] = round(
                            self._acc[key] + (mw_value / 1000) * elapsed_hours, 4
                        )
            else:
                _LOGGER.debug(
                    "Skipping accumulation — gap of %.1f minutes is too large",
                    elapsed_hours * 60,
                )

        # Hybrid: prefer the API chart total when it is >= our accumulator.
        # If the API has reset mid-day its value will be lower — ignore it.
        if api_totals:
            for key in self._TOTAL_KEYS:
                api_val = api_totals.get(key)
                if api_val is not None and api_val >= self._acc[key]:
                    self._acc[key] = api_val
                elif api_val is not None:
                    _LOGGER.debug(
                        "API chart total for %s (%.3f) is lower than accumulator "
                        "(%.3f) — ignoring API value (likely mid-day history reset)",
                        key,
                        api_val,
                        self._acc[key],
                    )

        self._last_poll_time = now
        return replace(
            data,
            totals={k: self._acc[k] for k in self._TOTAL_KEYS},
        )


def _fetch_powervault_data(  # pylint: disable=too-many-branches
    client: PowerVault,
    unit_id: str | None,
    local_ip: str | None = None,
    local_platform: str | None = None,
) -> PowervaultData:
    """Process and update powervault data."""
    if local_ip:
        return _fetch_powervault_data_legacy(client, local_platform)
    return _fetch_powervault_data_cloud(client, unit_id)  # type: ignore[arg-type]


def _fetch_powervault_data_legacy(  # pylint: disable=too-many-locals,too-many-statements
    client: PowerVault,
    local_platform: str | None,
) -> PowervaultData:
    """Fetch data from a legacy P3 Powervault unit via the local REST API."""
    if local_platform not in LEGACY_PLATFORMS:
        raise ServerError("Legacy Powervault platform is not configured")

    legacy_platform = local_platform

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

    common_telemetry, battery_diagnostics, detailed_battery = (
        _classify_legacy_telemetry(
            telemetry,
            legacy_platform,
        )
    )

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

    # Solar-first instant breakdown
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
    # totals are left empty here; PowervaultDataManager._accumulate populates them.
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
        totals={},
        common_telemetry=common_telemetry,
        battery_diagnostics=battery_diagnostics,
        detailed_battery=detailed_battery,
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
        common_telemetry={},
        battery_diagnostics={},
        detailed_battery={},
    )


def _classify_legacy_telemetry(
    telemetry: dict[str, object],
    local_platform: str,
) -> tuple[
    dict[str, TelemetryValue],
    dict[str, TelemetryValue],
    dict[str, dict[str, TelemetryValue]],
]:
    """Split legacy telemetry into common, summary, and detailed groups."""
    common_telemetry: dict[str, TelemetryValue] = {}
    battery_diagnostics: dict[str, TelemetryValue] = {}
    detailed_battery: dict[str, dict[str, TelemetryValue]] = {}

    for key in (
        "gridCurrent",
        "batteryCurrent",
        "inverterVoltage",
        "inverterFrequency",
        "maxChargePower",
        "maxDischargePower",
        "temperature",
        "cpuTemperature",
        "vocTemperature",
        "vocHumidity",
        "vocCO2",
        "vocVOC",
        "actualState",
    ):
        value = telemetry.get(key)
        if isinstance(value, str | int | float):
            common_telemetry[key] = value

    soc_average = telemetry.get("socAverage")
    if isinstance(soc_average, int | float):
        battery_diagnostics["socAverage"] = soc_average

    if local_platform == LEGACY_PLATFORM_P3:
        battery_diagnostics.update(_build_p3_battery_diagnostics(telemetry))
        detailed_battery.update(_build_p3_detailed_battery(telemetry))
    elif local_platform == LEGACY_PLATFORM_P3X:
        battery_diagnostics.update(_build_p3x_battery_diagnostics(telemetry))
        detailed_battery.update(_build_p3x_detailed_battery(telemetry))

    return common_telemetry, battery_diagnostics, detailed_battery


def _build_summary_metrics(
    prefix: str,
    values: list[float],
    *,
    precision: int,
) -> dict[str, float]:
    """Return min/max/avg summary metrics for a numeric series."""
    if not values:
        return {}

    return {
        f"{prefix}_min": round(min(values), precision),
        f"{prefix}_max": round(max(values), precision),
        f"{prefix}_avg": round(sum(values) / len(values), precision),
    }


def _matching_numeric_values(
    telemetry: dict[str, object],
    pattern: re.Pattern[str],
) -> list[float]:
    """Return numeric telemetry values that match a measurement pattern."""
    return [
        float(value)
        for key, value in telemetry.items()
        if pattern.match(key) and isinstance(value, int | float)
    ]


def _build_p3_battery_diagnostics(
    telemetry: dict[str, object],
) -> dict[str, TelemetryValue]:
    """Build summary battery telemetry for legacy P3 hardware."""
    diagnostics: dict[str, TelemetryValue] = {}
    diagnostics.update(
        _build_summary_metrics(
            "pack_temperature",
            _matching_numeric_values(telemetry, P3_PACK_TEMPERATURE_RE),
            precision=1,
        )
    )
    diagnostics.update(
        _build_summary_metrics(
            "backplane_temperature",
            _matching_numeric_values(telemetry, P3_BACKPLANE_TEMPERATURE_RE),
            precision=1,
        )
    )
    diagnostics.update(
        _build_summary_metrics(
            "string_cell_voltage",
            _matching_numeric_values(telemetry, P3_STRING_VOLTAGE_RE),
            precision=3,
        )
    )
    diagnostics.update(
        _build_summary_metrics(
            "string_cell_temperature",
            _matching_numeric_values(telemetry, P3_STRING_TEMPERATURE_RE),
            precision=1,
        )
    )
    return diagnostics


def _build_p3_detailed_battery(
    telemetry: dict[str, object],
) -> dict[str, dict[str, TelemetryValue]]:
    """Group detailed per-string telemetry for legacy P3 hardware."""
    grouped: dict[str, dict[str, TelemetryValue]] = {}
    for key, value in telemetry.items():
        if not isinstance(value, int | float):
            continue
        if match := P3_STRING_CELL_RE.match(key):
            grouped.setdefault(match.group(1), {})[key] = value
    return grouped


def _build_p3x_battery_diagnostics(
    telemetry: dict[str, object],
) -> dict[str, TelemetryValue]:
    """Build summary battery telemetry for legacy P3X hardware."""
    diagnostics: dict[str, TelemetryValue] = {}
    for key in (
        "pylontechMinCellVoltage",
        "pylontechMaxCellVoltage",
        "pylontechMinCellTemperature",
        "pylontechMaxCellTemperature",
        "pylontechAvgCellTemperature",
        "pylontechMinBMSTemperature",
        "pylontechMaxBMSTemperature",
        "pylontechAvgBMSTemperature",
        "pylontechMinMOSFETTemperature",
        "pylontechMaxMOSFETTemperature",
        "pylontechAvgMOSFETTemperature",
    ):
        value = telemetry.get(key)
        if isinstance(value, int | float):
            diagnostics[key] = value
    return diagnostics


def _build_p3x_detailed_battery(
    telemetry: dict[str, object],
) -> dict[str, dict[str, TelemetryValue]]:
    """Group detailed per-module telemetry for legacy P3X hardware."""
    grouped: dict[str, dict[str, TelemetryValue]] = {}
    for key, value in telemetry.items():
        if not isinstance(value, int | float):
            continue
        if match := P3X_MODULE_CELL_RE.match(key):
            grouped.setdefault(match.group(1), {})[key] = value
    return grouped
