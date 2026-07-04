"""Support for Powervault buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_IP_ADDRESS, DOMAIN, POWERVAULT_MANAGER
from .entity import PowervaultEntity
from .models import PowervaultRuntimeData


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Powervault button entities."""
    powervault_data: PowervaultRuntimeData = hass.data[DOMAIN][config_entry.entry_id]

    if config_entry.data.get(CONF_IP_ADDRESS):
        async_add_entities([PowervaultResetTotalsButton(powervault_data)])


class PowervaultResetTotalsButton(PowervaultEntity, ButtonEntity):
    """Button to clear cached local totals and refresh from current history."""

    _attr_name = "Powervault Reset Cached Totals"
    _attr_icon = "mdi:counter"

    def __init__(self, powervault_data: PowervaultRuntimeData) -> None:
        """Initialize the button."""
        super().__init__(powervault_data)
        self._manager = powervault_data[POWERVAULT_MANAGER]

    @property
    def unique_id(self) -> str:
        """Device unique id."""
        return f"{self.base_unique_id}_reset_cached_totals"

    def press(self) -> None:
        """Clear cached totals and schedule an immediate refresh."""
        self.hass.async_create_task(self._async_reset_and_refresh())

    async def async_press(self) -> None:
        """Clear cached totals and force an immediate refresh."""
        await self._async_reset_and_refresh()

    async def _async_reset_and_refresh(self) -> None:
        """Run the cached total reset flow."""
        await self._manager.async_reset_cached_totals()
        await self.coordinator.async_request_refresh()
