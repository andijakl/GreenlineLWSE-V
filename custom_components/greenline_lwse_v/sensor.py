"""Sensor platform for the Greenline LWSE-V integration."""

from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DAP_WW_CURRENT_TEMPERATURE, DAP_WW_TARGET_TEMPERATURE
from .coordinator import GreenlineLWSEConfigEntry, GreenlineLWSECoordinator
from .entity import GreenlineLWSEEntity, parse_temperature

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class GreenlineLWSESensorEntityDescription(SensorEntityDescription):
    """Describe a Greenline sensor entity."""

    dap: str


SENSOR_DESCRIPTIONS: tuple[GreenlineLWSESensorEntityDescription, ...] = (
    GreenlineLWSESensorEntityDescription(
        key="warm_water_temperature",
        translation_key="warm_water_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        dap=DAP_WW_CURRENT_TEMPERATURE,
    ),
    GreenlineLWSESensorEntityDescription(
        key="warm_water_target_temperature",
        translation_key="warm_water_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        dap=DAP_WW_TARGET_TEMPERATURE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GreenlineLWSEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor entities."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        GreenlineLWSESensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class GreenlineLWSESensor(GreenlineLWSEEntity, SensorEntity):
    """Representation of a Greenline warm-water temperature sensor."""

    entity_description: GreenlineLWSESensorEntityDescription

    def __init__(
        self,
        coordinator: GreenlineLWSECoordinator,
        description: GreenlineLWSESensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, f"{coordinator.device_id}_{description.key}")
        self.entity_description = description

    @property
    @override
    def native_value(self) -> float | None:
        """Return the current value reported by the device."""
        return parse_temperature(self.coordinator.data.get(self.entity_description.dap))
