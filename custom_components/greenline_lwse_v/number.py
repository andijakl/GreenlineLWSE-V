"""Number platform for the Greenline LWSE-V integration."""

from dataclasses import dataclass
from typing import override

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DAP_HK_TARGET_TEMPERATURE_REDUCED,
    DAP_WW_TARGET_TEMPERATURE,
    DAP_WW_TARGET_TEMPERATURE_REDUCED,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
    WW_TEMPERATURE_MAX,
    WW_TEMPERATURE_MIN,
)
from .coordinator import GreenlineLWSEConfigEntry, GreenlineLWSECoordinator
from .entity import GreenlineLWSEEntity, parse_temperature

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class GreenlineLWSENumberEntityDescription(NumberEntityDescription):
    """Describe a Greenline temperature setpoint."""

    dap: str


NUMBER_DESCRIPTIONS: tuple[GreenlineLWSENumberEntityDescription, ...] = (
    GreenlineLWSENumberEntityDescription(
        key="hk1_reduced_temperature",
        translation_key="reduced_temperature",
        native_min_value=TEMPERATURE_MIN,
        native_max_value=TEMPERATURE_MAX,
        dap=DAP_HK_TARGET_TEMPERATURE_REDUCED,
    ),
    GreenlineLWSENumberEntityDescription(
        key="warm_water_target_temperature",
        translation_key="warm_water_target_temperature",
        native_min_value=WW_TEMPERATURE_MIN,
        native_max_value=WW_TEMPERATURE_MAX,
        dap=DAP_WW_TARGET_TEMPERATURE,
    ),
    GreenlineLWSENumberEntityDescription(
        key="warm_water_reduced_temperature",
        translation_key="warm_water_reduced_temperature",
        native_min_value=WW_TEMPERATURE_MIN,
        native_max_value=WW_TEMPERATURE_MAX,
        dap=DAP_WW_TARGET_TEMPERATURE_REDUCED,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GreenlineLWSEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        GreenlineLWSENumber(coordinator, description)
        for description in NUMBER_DESCRIPTIONS
    )


class GreenlineLWSENumber(GreenlineLWSEEntity, NumberEntity):
    """Representation of a Greenline temperature setpoint."""

    entity_description: GreenlineLWSENumberEntityDescription
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: GreenlineLWSECoordinator,
        description: GreenlineLWSENumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, f"{coordinator.device_id}_{description.key}")
        self.entity_description = description

    @property
    @override
    def native_value(self) -> float | None:
        """Return the configured setpoint."""
        return parse_temperature(self.coordinator.data.get(self.entity_description.dap))

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Send the new setpoint to the device."""
        await self._async_set_value(self.entity_description.dap, value)
