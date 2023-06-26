"""Base class for powervault entities."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    MANUFACTURER,
    POWERVAULT_API,
    POWERVAULT_BASE_INFO,
    POWERVAULT_COORDINATOR,
)
from .models import PowervaultData, PowervaultRuntimeData


class PowervaultEntity(CoordinatorEntity[DataUpdateCoordinator[PowervaultData]]):
    """Base class for powervault entities."""

    base_unique_id: str

    def __init__(self, powervault_data: PowervaultRuntimeData) -> None:
        """Initialize the entity."""
        base_info = powervault_data[POWERVAULT_BASE_INFO]
        coordinator = powervault_data[POWERVAULT_COORDINATOR]
        assert coordinator is not None
        super().__init__(coordinator)
        self.powervault = powervault_data[POWERVAULT_API]
        # The serial numbers of the powervaults are unique to every site
        self.base_unique_id = "_".join(base_info.id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.base_unique_id)},
            manufacturer=MANUFACTURER,
            model=base_info.model,
            name=base_info.id,
            sw_version=base_info.eprom_id,
        )

    @property
    def data(self) -> PowervaultData:
        """Return the coordinator data."""
        return self.coordinator.data  # type: ignore[no-any-return]
