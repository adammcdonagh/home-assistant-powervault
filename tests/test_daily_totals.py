"""Regression tests for Powervault daily totals."""

# pylint: disable=protected-access

from __future__ import annotations

import asyncio
from datetime import date
from datetime import datetime as real_dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from custom_components.powervault import PowervaultDataManager, _try_fetch_chart_totals
from custom_components.powervault.models import PowervaultData


def _make_data() -> PowervaultData:
    """Build a zeroed PowervaultData sample for accumulator tests."""
    return PowervaultData(
        charge=80,
        batteryInputFromGrid=0,
        batteryInputFromSolar=0,
        batteryOutputConsumedByHome=0,
        batteryOutputExported=0,
        homeConsumed=0,
        gridConsumedByHome=0,
        solarConsumedByHome=0,
        solarExported=0,
        instant_battery=0,
        instant_demand=0,
        instant_grid=0,
        solarGenerated=0,
        solarConsumption=0,
        instant_solar=0,
        battery_state="normal",
        totals={},
    )


def _make_manager(time_zone: str) -> PowervaultDataManager:
    """Build a minimally initialized data manager for unit tests."""
    manager = object.__new__(PowervaultDataManager)
    manager.hass = SimpleNamespace(config=SimpleNamespace(time_zone=time_zone))
    manager.client = Mock()
    manager.unit_id = None
    manager.local_ip = "192.168.0.10"
    manager.runtime_data = {}
    manager.config_entry = None
    manager._local_tz = ZoneInfo(time_zone)
    manager._acc = dict.fromkeys(PowervaultDataManager._TOTAL_KEYS, 12.0)
    manager._last_poll_time = None
    manager._acc_date = date(2026, 6, 10)
    manager._store = None
    return manager


def test_accumulate_resets_at_homeassistant_midnight() -> None:
    """Reset should follow Home Assistant's configured timezone."""
    manager = _make_manager("Europe/Helsinki")
    manager._last_poll_time = real_dt(2026, 6, 10, 23, 55, tzinfo=manager._local_tz)
    now_local = real_dt(2026, 6, 11, 0, 5, tzinfo=manager._local_tz)

    with patch("custom_components.powervault.dt", wraps=real_dt) as mock_dt:
        mock_dt.now.return_value = now_local
        result = manager._accumulate(_make_data(), api_totals=None)

    assert manager._acc_date == date(2026, 6, 11)
    assert result.totals["solarGenerated"] == 0.0
    assert result.totals["homeConsumed"] == 0.0


def test_try_fetch_chart_totals_discards_previous_day_samples() -> None:
    """Previous-day chart samples must not seed a new day's totals."""
    local_tz = ZoneInfo("Europe/London")
    stale_sample_time = real_dt(2026, 6, 30, 23, 55, tzinfo=local_tz).timestamp()
    client = Mock()
    client.get_chart_data.return_value = [
        [
            {
                "measurement": "gridPower",
                "timestamp": stale_sample_time,
                "value": 0,
            },
            {
                "measurement": "batteryPower",
                "timestamp": stale_sample_time,
                "value": 0,
            },
            {
                "measurement": "aux1Power",
                "timestamp": stale_sample_time,
                "value": -2000,
            },
        ]
    ]

    with patch("custom_components.powervault.dt", wraps=real_dt) as mock_dt:
        mock_dt.now.return_value = real_dt(2026, 7, 1, 0, 2, tzinfo=local_tz)
        totals = _try_fetch_chart_totals(client, local_tz)

    assert totals is None


def test_try_fetch_chart_totals_handles_flat_chart_samples() -> None:
    """Flat chart-data samples from the client library should be accepted."""
    local_tz = ZoneInfo("Europe/London")
    client = Mock()
    client.get_chart_data.return_value = [
        {
            "timestamp": real_dt(2026, 7, 1, 0, 5, tzinfo=local_tz).timestamp(),
            "gridPower": 120,
            "batteryPower": 0,
            "aux1Power": 0,
        },
        {
            "timestamp": real_dt(2026, 7, 1, 0, 10, tzinfo=local_tz).timestamp(),
            "gridPower": 150,
            "batteryPower": 0,
            "aux1Power": 0,
        },
    ]

    with patch("custom_components.powervault.dt", wraps=real_dt) as mock_dt:
        mock_dt.now.return_value = real_dt(2026, 7, 1, 0, 10, tzinfo=local_tz)
        totals = _try_fetch_chart_totals(client, local_tz)

    assert totals is not None
    assert totals["solarGenerated"] == 0.0
    assert totals["gridConsumedByHome"] > 0.0


def test_async_reset_cached_totals_clears_accumulator_and_store() -> None:
    """Manual reset should clear both in-memory and persisted accumulator state."""
    manager = _make_manager("Europe/London")
    manager._acc["solarGenerated"] = 12.5
    manager._last_poll_time = real_dt(2026, 7, 1, 1, 0, tzinfo=manager._local_tz)
    manager._store = AsyncMock()

    with patch("custom_components.powervault.dt", wraps=real_dt) as mock_dt:
        mock_dt.now.return_value = real_dt(2026, 7, 1, 1, 20, tzinfo=manager._local_tz)
        asyncio.run(manager.async_reset_cached_totals())

    assert manager._acc["solarGenerated"] == 0.0
    assert manager._last_poll_time is None
    assert manager._acc_date == date(2026, 7, 1)
    manager._store.async_remove.assert_awaited_once()
