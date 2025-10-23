"""Support for Powervault charge status selection."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from powervaultpy import VALID_STATUSES, PowerVault

from .const import DOMAIN
from .entity import PowervaultEntity
from .models import PowervaultRuntimeData


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Powervault charge status select entities."""
    powervault_data: PowerVault = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([PowervaultSelectEntity(powervault_data)])


class PowervaultSelectEntity(PowervaultEntity, SelectEntity):  # pylint: disable=abstract-method
    """Representation of a Powervault select entity."""

    def __init__(
        self,
        powervault_data: PowervaultRuntimeData,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(powervault_data)

        self._attr_name = "Powervault Charge Status"
        self._attr_unique_id = f"{self.base_unique_id}_charge_status"
        self._attr_options = VALID_STATUSES

        self._async_update_attrs()

    @callback  # type: ignore[misc]
    def _async_update_attrs(self) -> None:
        """Update entity attributes."""
        self._attr_current_option = self.data.battery_state

    @callback  # type: ignore[misc]
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Change the current preset."""
        await self.coordinator.hass.async_add_executor_job(
            self.powervault.set_battery_state,
            self.coordinator.config_entry.data["unit_id"],
            option,
        )

        self._attr_current_option = option
        self.async_write_ha_state()
