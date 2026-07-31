"""Climate platform for the Greenline LWSE-V integration."""

from typing import Any, override

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DAP_HK_COOLING_ACTIVE,
    DAP_HK_COOLING_ENABLED,
    DAP_HK_CURRENT_TEMPERATURE,
    DAP_HK_HEATING_ACTIVE,
    DAP_HK_HEATING_ENABLED,
    DAP_HK_TARGET_TEMPERATURE,
    TEMPERATURE_MAX,
    TEMPERATURE_MIN,
)
from .coordinator import GreenlineLWSEConfigEntry, GreenlineLWSECoordinator
from .entity import GreenlineLWSEEntity, parse_temperature

PARALLEL_UPDATES = 0

_HVAC_MODE_TO_FLAGS = {
    HVACMode.HEAT_COOL: ("1", "1"),
    HVACMode.HEAT: ("1", "0"),
    HVACMode.COOL: ("0", "1"),
    HVACMode.OFF: ("0", "0"),
}
_FLAGS_TO_HVAC_MODE = {flags: mode for mode, flags in _HVAC_MODE_TO_FLAGS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GreenlineLWSEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entity."""
    async_add_entities([GreenlineLWSEClimate(config_entry.runtime_data)])


class GreenlineLWSEClimate(GreenlineLWSEEntity, ClimateEntity):
    """Representation of the HK1 heating circuit."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.HEAT_COOL,
    ]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = TEMPERATURE_MIN
    _attr_max_temp = TEMPERATURE_MAX
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: GreenlineLWSECoordinator) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, f"{coordinator.device_id}_hk1")

    @property
    @override
    def current_temperature(self) -> float | None:
        """Return the current room temperature."""
        return parse_temperature(self.coordinator.data.get(DAP_HK_CURRENT_TEMPERATURE))

    @property
    @override
    def target_temperature(self) -> float | None:
        """Return the desired room temperature."""
        return parse_temperature(self.coordinator.data.get(DAP_HK_TARGET_TEMPERATURE))

    @property
    @override
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode."""
        heating = self.coordinator.data.get(DAP_HK_HEATING_ENABLED)
        cooling = self.coordinator.data.get(DAP_HK_COOLING_ENABLED)
        if heating is None or cooling is None:
            return HVACMode.OFF
        return _FLAGS_TO_HVAC_MODE.get((heating, cooling), HVACMode.OFF)

    @property
    @override
    def hvac_action(self) -> HVACAction | None:
        """Return whether the circuit is heating, cooling, or idle."""
        if self.hvac_mode is HVACMode.OFF:
            return HVACAction.OFF
        if self.coordinator.data.get(DAP_HK_HEATING_ACTIVE) == "1":
            return HVACAction.HEATING
        if self.coordinator.data.get(DAP_HK_COOLING_ACTIVE) == "1":
            return HVACAction.COOLING
        return HVACAction.IDLE

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the desired room temperature."""
        await self._async_set_value(DAP_HK_TARGET_TEMPERATURE, kwargs[ATTR_TEMPERATURE])

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Enable or disable heating and cooling."""
        heating_flag, cooling_flag = _HVAC_MODE_TO_FLAGS[hvac_mode]
        await self._async_set_value(DAP_HK_HEATING_ENABLED, heating_flag)
        await self._async_set_value(DAP_HK_COOLING_ENABLED, cooling_flag)
