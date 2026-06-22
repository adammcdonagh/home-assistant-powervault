"""Support for Powervault switches."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_IP_ADDRESS, CONF_USE_API_HISTORY, DOMAIN
from .entity import PowervaultEntity
from .models import PowervaultRuntimeData


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Powervault switch entities."""
    powervault_data: PowervaultRuntimeData = hass.data[DOMAIN][config_entry.entry_id]

    # History collection only applies to the local P3 path.
    if config_entry.data.get(CONF_IP_ADDRESS):
        async_add_entities([PowervaultHistorySwitch(powervault_data)])


class PowervaultHistorySwitch(PowervaultEntity, SwitchEntity):
    """Switch to enable/disable API history collection for energy totals.

    When on (default), each poll attempts to fetch today's chart history from
    the Powervault API and uses it to improve the accuracy of the energy total
    sensors.  When off, only the incremental accumulator (calculated from
    instantaneous readings) is used — useful if the API history is unreliable.
    """

    _attr_name = "Powervault Use API History"
    _attr_icon = "mdi:chart-timeline-variant"

    @property
    def unique_id(self) -> str:
        """Device unique id."""
        return f"{self.base_unique_id}_use_api_history"

    @property
    def is_on(self) -> bool:
        """Return true when API history collection is enabled."""
        return self.coordinator.config_entry.options.get(CONF_USE_API_HISTORY, True)  # type: ignore[no-any-return]

    async def async_turn_on(self, **_kwargs: object) -> None:
        """Enable API history collection."""
        await self._set(enabled=True)

    async def async_turn_off(self, **_kwargs: object) -> None:
        """Disable API history collection, forcing dynamic accumulation only."""
        await self._set(enabled=False)

    async def _set(self, *, enabled: bool) -> None:
        entry = self.coordinator.config_entry
        self.hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_USE_API_HISTORY: enabled},
        )
        self.async_write_ha_state()
