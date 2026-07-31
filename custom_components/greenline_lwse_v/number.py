"""Number platform for the Greenline LWSE-V integration."""

from typing import override

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DAP_HK_TARGET_TEMPERATURE_REDUCED, TEMPERATURE_MAX, TEMPERATURE_MIN
from .coordinator import GreenlineLWSEConfigEntry, GreenlineLWSECoordinator
from .entity import GreenlineLWSEEntity, parse_temperature

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GreenlineLWSEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entity."""
    async_add_entities([GreenlineLWSEReducedTemperature(config_entry.runtime_data)])


class GreenlineLWSEReducedTemperature(GreenlineLWSEEntity, NumberEntity):
    """Representation of the reduced room-temperature setpoint."""

    _attr_translation_key = "reduced_temperature"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = TEMPERATURE_MIN
    _attr_native_max_value = TEMPERATURE_MAX
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: GreenlineLWSECoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(
            coordinator, f"{coordinator.device_id}_hk1_reduced_temperature"
        )

    @property
    @override
    def native_value(self) -> float | None:
        """Return the configured reduced room temperature."""
        return parse_temperature(
            self.coordinator.data.get(DAP_HK_TARGET_TEMPERATURE_REDUCED)
        )

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the reduced room temperature."""
        await self._async_set_value(DAP_HK_TARGET_TEMPERATURE_REDUCED, value)
