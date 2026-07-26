"""Unit tests for Powervault button entities."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

from custom_components.powervault.button import (
    PowervaultCancelOverrideButton,
    PowervaultResetTotalsButton,
    async_setup_entry,
)
from custom_components.powervault.const import (
    CONF_IP_ADDRESS,
    DOMAIN,
    POWERVAULT_API,
    POWERVAULT_BASE_INFO,
    POWERVAULT_COORDINATOR,
    POWERVAULT_MANAGER,
)
from custom_components.powervault.models import PowervaultBaseInfo


def _make_runtime_data(
    config_data: dict[str, object],
) -> tuple[dict[str, object], Mock, AsyncMock]:
    """Build minimal runtime data for button entity tests."""
    client = Mock()
    refresh = AsyncMock()

    async def async_add_executor_job(func: Callable[..., Any], *args: object) -> Any:
        return func(*args)

    coordinator = SimpleNamespace(
        data=None,
        hass=SimpleNamespace(async_add_executor_job=async_add_executor_job),
        config_entry=SimpleNamespace(data=config_data),
        async_request_refresh=refresh,
    )
    runtime_data = {
        POWERVAULT_API: client,
        POWERVAULT_BASE_INFO: PowervaultBaseInfo(
            id="pv-site-1",
            model="Powervault",
            eprom_id="eprom-1",
        ),
        POWERVAULT_COORDINATOR: coordinator,
        POWERVAULT_MANAGER: Mock(),
    }
    return runtime_data, client, refresh


def test_async_setup_entry_adds_cancel_button_for_cloud_units() -> None:
    """Cloud units should expose the cancel override button."""
    runtime_data, _, _ = _make_runtime_data({"unit_id": "unit-1"})
    hass = SimpleNamespace(data={DOMAIN: {"entry-1": runtime_data}})
    add_entities = Mock()

    asyncio.run(
        async_setup_entry(
            hass,
            SimpleNamespace(entry_id="entry-1", data={"unit_id": "unit-1"}),
            add_entities,
        )
    )

    entities = add_entities.call_args.args[0]
    assert len(entities) == 1
    assert isinstance(entities[0], PowervaultCancelOverrideButton)


def test_async_setup_entry_adds_both_buttons_for_local_units() -> None:
    """Local units should expose reset totals and cancel override buttons."""
    runtime_data, _, _ = _make_runtime_data({CONF_IP_ADDRESS: "192.168.0.20"})
    hass = SimpleNamespace(data={DOMAIN: {"entry-1": runtime_data}})
    add_entities = Mock()

    asyncio.run(
        async_setup_entry(
            hass,
            SimpleNamespace(entry_id="entry-1", data={CONF_IP_ADDRESS: "192.168.0.20"}),
            add_entities,
        )
    )

    entities = add_entities.call_args.args[0]
    assert len(entities) == 2
    assert isinstance(entities[0], PowervaultResetTotalsButton)
    assert isinstance(entities[1], PowervaultCancelOverrideButton)


def test_cancel_override_button_calls_client_with_cancel_flag() -> None:
    """Cancel button should request a normal-state override with cancel enabled."""
    runtime_data, client, refresh = _make_runtime_data({"unit_id": "unit-1"})

    button = PowervaultCancelOverrideButton(runtime_data)

    asyncio.run(button.async_press())

    client.set_battery_state.assert_called_once_with("unit-1", "normal", True)
    refresh.assert_awaited_once()
