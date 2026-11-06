"""Sensor platform for the Greenline LWSE-V integration."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import (
    DAP_BACKUP_HEATER_HOURS,
    DAP_COMPRESSOR_HOURS,
    DAP_COMPRESSOR_STARTS,
    DAP_FLOW_RATE,
    DAP_FLOW_TEMPERATURE,
    DAP_HEAT_ENERGY_COOLING,
    DAP_HEAT_ENERGY_HEATING,
    DAP_HEAT_ENERGY_TOTAL,
    DAP_HEAT_ENERGY_WARM_WATER,
    DAP_HEAT_OUTPUT,
    DAP_HEAT_PUMP_STATE,
    DAP_HEATING_MODE,
    DAP_OUTDOOR_TEMPERATURE,
    DAP_RETURN_TEMPERATURE,
    DAP_WW_CURRENT_TEMPERATURE,
)
from .coordinator import GreenlineLWSEConfigEntry, GreenlineLWSECoordinator
from .entity import GreenlineLWSEEntity, parse_number

PARALLEL_UPDATES = 0

# Controller list values of the heat pump state ("Wärmepumpe" in the heating status).
HEAT_PUMP_STATES = {
    "0": "manual_operation",
    "1": "compressor_alarm",
    "2": "tariff_lockout",
    "3": "compressor_substitution",
    "4": "restart_delay",
    "5": "defrosting",
    "6": "heat_generator_pump_delay",
    "7": "source_pump_fan_delay",
    "8": "bivalence_lockout",
    "9": "external_release_off",
    "10": "overtemperature",
    "11": "stage_1_off",
    "12": "external_release_on",
    "13": "frost_protection",
    "14": "active_cooling",
    "15": "warm_water_1",
    "16": "warm_water_2",
    "17": "warm_water_1_and_2",
    "18": "heating",
    "19": "pool",
    "20": "standby",
    "21": "compressor_off",
}

# Controller list values of the heating mode ("Heizung Modus").
HEATING_MODES = {
    "0": "standby",
    "1": "summer",
    "2": "reduced",
    "3": "normal",
    "4": "automatic",
}


def _number(dap: str) -> Callable[[Mapping[str, str]], StateType]:
    return lambda data: parse_number(data.get(dap))


def _sum(daps: tuple[str, ...]) -> Callable[[Mapping[str, str]], StateType]:
    def value(data: Mapping[str, str]) -> StateType:
        numbers = [parse_number(data.get(dap)) for dap in daps]
        return None if None in numbers else sum(n for n in numbers if n is not None)

    return value


def _option(
    dap: str, options: Mapping[str, str]
) -> Callable[[Mapping[str, str]], StateType]:
    return lambda data: options.get(data.get(dap, ""))


@dataclass(frozen=True, kw_only=True)
class GreenlineLWSESensorEntityDescription(SensorEntityDescription):
    """Describe a Greenline sensor entity."""

    value_fn: Callable[[Mapping[str, str]], StateType]


def _temperature(key: str, dap: str) -> GreenlineLWSESensorEntityDescription:
    return GreenlineLWSESensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_number(dap),
    )


def _heat_energy(
    key: str, value_fn: Callable[[Mapping[str, str]], StateType]
) -> GreenlineLWSESensorEntityDescription:
    return GreenlineLWSESensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=value_fn,
    )


def _operating_hours(key: str, dap: str) -> GreenlineLWSESensorEntityDescription:
    return GreenlineLWSESensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_number(dap),
    )


SENSOR_DESCRIPTIONS: tuple[GreenlineLWSESensorEntityDescription, ...] = (
    _temperature("warm_water_temperature", DAP_WW_CURRENT_TEMPERATURE),
    GreenlineLWSESensorEntityDescription(
        key="heat_pump_state",
        translation_key="heat_pump_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(HEAT_PUMP_STATES.values()),
        value_fn=_option(DAP_HEAT_PUMP_STATE, HEAT_PUMP_STATES),
    ),
    GreenlineLWSESensorEntityDescription(
        key="heating_mode",
        translation_key="heating_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(HEATING_MODES.values()),
        value_fn=_option(DAP_HEATING_MODE, HEATING_MODES),
    ),
    GreenlineLWSESensorEntityDescription(
        key="heat_output",
        translation_key="heat_output",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_number(DAP_HEAT_OUTPUT),
    ),
    GreenlineLWSESensorEntityDescription(
        key="flow_rate",
        translation_key="flow_rate",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_number(DAP_FLOW_RATE),
    ),
    _heat_energy("heat_energy", _number(DAP_HEAT_ENERGY_TOTAL)),
    _heat_energy("heat_energy_heating", _sum(DAP_HEAT_ENERGY_HEATING)),
    _heat_energy("heat_energy_warm_water", _number(DAP_HEAT_ENERGY_WARM_WATER)),
    _heat_energy("heat_energy_cooling", _number(DAP_HEAT_ENERGY_COOLING)),
    _temperature("outdoor_temperature", DAP_OUTDOOR_TEMPERATURE),
    _temperature("flow_temperature", DAP_FLOW_TEMPERATURE),
    _temperature("return_temperature", DAP_RETURN_TEMPERATURE),
    GreenlineLWSESensorEntityDescription(
        key="compressor_starts",
        translation_key="compressor_starts",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_number(DAP_COMPRESSOR_STARTS),
    ),
    _operating_hours("compressor_operating_hours", DAP_COMPRESSOR_HOURS),
    _operating_hours("backup_heater_operating_hours", DAP_BACKUP_HEATER_HOURS),
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
    """Representation of a Greenline sensor."""

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
    def native_value(self) -> StateType:
        """Return the current value reported by the device."""
        return self.entity_description.value_fn(self.coordinator.data)
