"""Unit tests for Powervault local telemetry parsing and platform persistence."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from custom_components.powervault import (
    _async_ensure_legacy_platform,
    _fetch_base_info_legacy,
    _fetch_powervault_data_legacy,
)
from custom_components.powervault.const import (
    CONF_IP_ADDRESS,
    CONF_PLATFORM,
    LEGACY_PLATFORM_P3,
    LEGACY_PLATFORM_P3X,
)
from custom_components.powervault.sensor import (
    _battery_group_voltage_aggregates,
    _group_voltage_summary,
)


def _load_example_telemetry() -> list[dict[str, object]]:
    """Load the checked-in P3X telemetry sample."""
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "powervault"
        / "example-telemetry.json"
    )
    return cast(
        list[dict[str, object]],
        json.loads(fixture_path.read_text(encoding="utf-8")),
    )


def test_fetch_powervault_data_legacy_p3x_parses_common_and_battery_telemetry() -> None:
    """P3X local telemetry should populate additive telemetry buckets."""
    client = Mock()
    client.get_data.return_value = _load_example_telemetry()
    client.get_battery_state.return_value = "normal"

    data = _fetch_powervault_data_legacy(client, LEGACY_PLATFORM_P3X)

    assert data.charge == 55
    assert data.common_telemetry["gridCurrent"] == 3.3799999999999999
    assert data.common_telemetry["maxChargePower"] == 11981
    assert data.battery_diagnostics["socAverage"] == 58
    assert data.battery_diagnostics["pylontechMaxCellVoltage"] == 3.3380000000000001
    assert "pylontechModule10" in data.detailed_battery
    assert (
        data.detailed_battery["pylontechModule10"]["pylontechModule10cell0Voltage"]
        == 3.3359999999999999
    )

    module_summary = _group_voltage_summary(data.detailed_battery["pylontechModule10"])
    assert module_summary == {
        "total_voltage": 50.026,
        "average_cell_voltage": 3.335,
        "maximum_cell_voltage": 3.338,
    }

    aggregate_summary = _battery_group_voltage_aggregates(data.detailed_battery)
    assert aggregate_summary == {
        "average_total_voltage": 49.987,
        "maximum_total_voltage": 50.026,
    }


def test_fetch_powervault_data_legacy_p3_derives_summary_metrics() -> None:
    """P3 local telemetry should derive pack, backplane, and string summaries."""
    client = Mock()
    client.get_data.return_value = [
        {"measurement": "socUsable", "value": 64},
        {"measurement": "socAverage", "value": 66},
        {"measurement": "gridPower", "value": 250},
        {"measurement": "batteryPower", "value": -400},
        {"measurement": "aux1Power", "value": -900},
        {"measurement": "pack0Temperature", "value": 21.2},
        {"measurement": "pack1Temperature", "value": 26.7},
        {"measurement": "backplane0Temperature", "value": 19.4},
        {"measurement": "backplane1Temperature", "value": 22.8},
        {"measurement": "string0cell0Voltage", "value": 3.301},
        {"measurement": "string0cell1Voltage", "value": 3.315},
        {"measurement": "string1cell0Voltage", "value": 3.289},
        {"measurement": "string0cell0Temperature", "value": 22.4},
        {"measurement": "string0cell1Temperature", "value": 23.1},
        {"measurement": "string1cell0Temperature", "value": 24.9},
    ]
    client.get_battery_state.return_value = "normal"

    data = _fetch_powervault_data_legacy(client, LEGACY_PLATFORM_P3)

    assert data.battery_diagnostics["socAverage"] == 66
    assert data.battery_diagnostics["pack_temperature_min"] == 21.2
    assert data.battery_diagnostics["pack_temperature_max"] == 26.7
    assert data.battery_diagnostics["pack_temperature_avg"] == 23.9
    assert data.battery_diagnostics["backplane_temperature_avg"] == 21.1
    assert data.battery_diagnostics["string_cell_voltage_min"] == 3.289
    assert data.battery_diagnostics["string_cell_voltage_max"] == 3.315
    assert data.battery_diagnostics["string_cell_voltage_avg"] == 3.302
    assert data.battery_diagnostics["string_cell_temperature_avg"] == 23.5
    assert "string0" in data.detailed_battery
    assert data.detailed_battery["string0"]["string0cell1Voltage"] == 3.315

    string_summary = _group_voltage_summary(data.detailed_battery["string0"])
    assert string_summary == {
        "total_voltage": 6.616,
        "average_cell_voltage": 3.308,
        "maximum_cell_voltage": 3.315,
    }

    aggregate_summary = _battery_group_voltage_aggregates(data.detailed_battery)
    assert aggregate_summary == {
        "average_total_voltage": 4.952,
        "maximum_total_voltage": 6.616,
    }


def test_async_ensure_legacy_platform_persists_detected_value() -> None:
    """Legacy local platform should be detected once and stored in config data."""

    async def async_add_executor_job(func: Callable[..., str], *args: object) -> str:
        return func(*args)

    update_entry = Mock()
    hass = SimpleNamespace(
        async_add_executor_job=async_add_executor_job,
        config_entries=SimpleNamespace(async_update_entry=update_entry),
    )
    entry = SimpleNamespace(data={CONF_IP_ADDRESS: "192.168.0.20"})
    client = Mock()
    client.get_platform.return_value = "P3X"

    platform = asyncio.run(_async_ensure_legacy_platform(hass, entry, client))

    assert platform == LEGACY_PLATFORM_P3X
    update_entry.assert_called_once_with(
        entry,
        data={
            CONF_IP_ADDRESS: "192.168.0.20",
            CONF_PLATFORM: LEGACY_PLATFORM_P3X,
        },
    )


def test_fetch_base_info_legacy_uses_uppercase_platform_as_model() -> None:
    """Legacy local device model should match the stored platform in uppercase."""
    client = Mock()
    client.get_unit_id.return_value = "pv-site-1"

    base_info = _fetch_base_info_legacy(client, LEGACY_PLATFORM_P3X)

    assert base_info.id == "pv-site-1"
    assert base_info.model == "Powervault P3X"
