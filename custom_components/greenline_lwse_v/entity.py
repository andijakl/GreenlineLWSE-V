"""Base entity for the Greenline LWSE-V integration."""

import math
from typing import override

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import GreenlineLWSEConnectionError
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import GreenlineLWSECoordinator


def parse_number(value: str | None) -> float | None:
    """Convert a raw device value to a finite number; whole numbers stay integers."""
    if value is None or value == "---":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


class GreenlineLWSEEntity(CoordinatorEntity[GreenlineLWSECoordinator]):
    """Base entity for the Greenline device tracked by an entry."""

    _attr_has_entity_name = True
    # Data points shown by the entity; subscribed only while the entity is enabled.
    _daps: tuple[str, ...] = ()

    def __init__(self, coordinator: GreenlineLWSECoordinator, unique_id: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name="Greenline LWSE-V",
            serial_number=coordinator.device_id,
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Subscribe to the entity's data points once it is enabled and added."""
        await super().async_added_to_hass()
        await self.coordinator.async_subscribe(self._daps)

    async def _async_set_value(self, dap: str, value: float | str) -> None:
        """Set a value on the device."""
        try:
            await self.coordinator.client.async_set_value(dap, value)
        except GreenlineLWSEConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_value_failed",
            ) from err
