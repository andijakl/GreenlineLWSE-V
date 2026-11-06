"""Test Greenline LWSE-V sensor entities."""

import pytest

from custom_components.greenline_lwse_v.const import (
    DAP_FLOW_TEMPERATURE,
    DAP_HEAT_ENERGY_HEATING,
    DAP_HEAT_OUTPUT,
    DAP_HEAT_PUMP_STATE,
    DAP_HEATING_MODE,
    DAP_OUTDOOR_TEMPERATURE,
    DAP_WW_CURRENT_TEMPERATURE,
)
from homeassistant.components.sensor import (
    ATTR_OPTIONS,
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNKNOWN,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .fake_controller import FakeController, wait_for

PREFIX = "sensor.greenline_lwse_v_"
STATE = f"{PREFIX}operating_state"


def _state(hass: HomeAssistant, name: str) -> str:
    state = hass.states.get(f"{PREFIX}{name}")
    assert state is not None, name
    return state.state


@pytest.mark.parametrize(
    ("name", "state", "unit", "state_class"),
    [
        ("warm_water_temperature", "47.2", "°C", SensorStateClass.MEASUREMENT),
        ("heat_output", "13244", "W", SensorStateClass.MEASUREMENT),
        ("flow_rate", "29.2", "L/min", SensorStateClass.MEASUREMENT),
        ("heat_energy", "96508", "kWh", SensorStateClass.TOTAL_INCREASING),
        ("heat_energy_heating", "78065", "kWh", SensorStateClass.TOTAL_INCREASING),
        ("heat_energy_warm_water", "19664", "kWh", SensorStateClass.TOTAL_INCREASING),
        ("heat_energy_cooling", "384", "kWh", SensorStateClass.TOTAL_INCREASING),
        ("outdoor_temperature", "7.3", "°C", SensorStateClass.MEASUREMENT),
        ("flow_temperature", "54.2", "°C", SensorStateClass.MEASUREMENT),
        ("return_temperature", "48.2", "°C", SensorStateClass.MEASUREMENT),
        ("compressor_starts", "12540", None, SensorStateClass.TOTAL_INCREASING),
        ("compressor_operating_hours", "10235", "h", SensorStateClass.TOTAL_INCREASING),
        (
            "backup_heater_operating_hours",
            "218",
            "h",
            SensorStateClass.TOTAL_INCREASING,
        ),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_measurements(
    hass: HomeAssistant,
    name: str,
    state: str,
    unit: str | None,
    state_class: SensorStateClass,
) -> None:
    """Test controller values are exposed with units suitable for statistics."""
    entity_state = hass.states.get(f"{PREFIX}{name}")
    assert entity_state is not None
    assert entity_state.state == state
    assert entity_state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == unit
    assert entity_state.attributes[ATTR_STATE_CLASS] == state_class


@pytest.mark.usefixtures("loaded_entry")
async def test_counters_are_diagnostic(hass: HomeAssistant) -> None:
    """Test service counters do not clutter the default dashboard."""
    registry = er.async_get(hass)
    for name in (
        "flow_rate",
        "compressor_starts",
        "compressor_operating_hours",
        "backup_heater_operating_hours",
    ):
        entry = registry.async_get(f"{PREFIX}{name}")
        assert entry is not None
        assert entry.entity_category is EntityCategory.DIAGNOSTIC
    assert registry.async_get(f"{PREFIX}heat_output").entity_category is None


@pytest.mark.usefixtures("loaded_entry")
async def test_operating_state_follows_controller(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test a warm-water cycle followed by defrosting and a restart delay."""
    state = hass.states.get(STATE)
    assert state is not None
    assert state.state == "warm_water_1"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENUM
    assert len(state.attributes[ATTR_OPTIONS]) == 22

    await fake_controller.push({DAP_HEAT_PUMP_STATE: "5", DAP_HEAT_OUTPUT: "0"})
    await wait_for(lambda: hass.states.get(STATE).state == "defrosting")
    assert _state(hass, "heat_output") == "0"

    await fake_controller.push({DAP_HEAT_PUMP_STATE: "4"})
    await wait_for(lambda: hass.states.get(STATE).state == "restart_delay")


@pytest.mark.usefixtures("loaded_entry")
async def test_unknown_controller_state(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test a state added by newer controller firmware is shown as unknown."""
    await fake_controller.push({DAP_HEAT_PUMP_STATE: "99"})

    await wait_for(lambda: hass.states.get(STATE).state == STATE_UNKNOWN)


@pytest.mark.usefixtures("loaded_entry")
async def test_heating_mode(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test the heating mode follows the controller."""
    assert _state(hass, "heating_mode") == "automatic"

    await fake_controller.push({DAP_HEATING_MODE: "1"})

    await wait_for(lambda: _state(hass, "heating_mode") == "summer")


@pytest.mark.usefixtures("loaded_entry")
async def test_heating_energy_sums_temperature_bands(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test heating energy combines the controller's flow-temperature bands."""
    await fake_controller.push({DAP_HEAT_ENERGY_HEATING[1]: "53071"})
    await wait_for(lambda: _state(hass, "heat_energy_heating") == "78067")

    await fake_controller.push({DAP_HEAT_ENERGY_HEATING[2]: "---"})
    await wait_for(lambda: _state(hass, "heat_energy_heating") == STATE_UNKNOWN)


@pytest.mark.usefixtures("loaded_entry")
async def test_temperatures_follow_controller(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test temperature pushes, including a disconnected sensor."""
    await fake_controller.push(
        {
            DAP_WW_CURRENT_TEMPERATURE: "46.8",
            DAP_OUTDOOR_TEMPERATURE: "-3.5",
            DAP_FLOW_TEMPERATURE: "---",
        }
    )

    await wait_for(lambda: _state(hass, "flow_temperature") == STATE_UNKNOWN)
    assert _state(hass, "warm_water_temperature") == "46.8"
    assert _state(hass, "outdoor_temperature") == "-3.5"
