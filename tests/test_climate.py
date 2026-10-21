"""Test the Greenline LWSE-V climate entity."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenline_lwse_v.const import (
    DAP_HK_COOLING_ACTIVE,
    DAP_HK_COOLING_ENABLED,
    DAP_HK_CURRENT_TEMPERATURE,
    DAP_HK_HEATING_ACTIVE,
    DAP_HK_HEATING_ENABLED,
    DAP_HK_TARGET_TEMPERATURE,
    DOMAIN,
)
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import TEST_DEVICE_ID
from .fake_controller import FakeController, wait_for

ENTITY_ID = "climate.greenline_lwse_v"


async def test_state_and_identifiers(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Test the climate state and serial-based identifiers."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING
    assert state.attributes[ATTR_TEMPERATURE] == 21.0
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 20.5

    entity_entry = er.async_get(hass).async_get(ENTITY_ID)
    assert entity_entry is not None
    assert entity_entry.unique_id == f"{TEST_DEVICE_ID}_hk1"
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, TEST_DEVICE_ID), loaded_entry.entry_id
    )
    assert device is not None
    assert entity_entry.device_id == device.id


@pytest.mark.usefixtures("loaded_entry")
async def test_missing_room_sensor(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test the controller's placeholder for a circuit without a room sensor."""
    await fake_controller.push({DAP_HK_CURRENT_TEMPERATURE: "---"})

    await wait_for(
        lambda: hass.states.get(ENTITY_ID).attributes[ATTR_CURRENT_TEMPERATURE] is None
    )
    assert hass.states.get(ENTITY_ID).attributes[ATTR_TEMPERATURE] == 21.0


@pytest.mark.usefixtures("loaded_entry")
async def test_set_temperature(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test a new target temperature is written and confirmed by the controller."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 22.5},
        blocking=True,
    )

    await wait_for(
        lambda: hass.states.get(ENTITY_ID).attributes[ATTR_TEMPERATURE] == 22.5
    )
    assert fake_controller.commands("setVMValue") == [
        {"dap": DAP_HK_TARGET_TEMPERATURE, "value": "22.5"}
    ]


@pytest.mark.parametrize(
    ("hvac_mode", "heating", "cooling"),
    [
        (HVACMode.HEAT_COOL, "1", "1"),
        (HVACMode.COOL, "0", "1"),
        (HVACMode.OFF, "0", "0"),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_set_hvac_mode(
    hass: HomeAssistant,
    fake_controller: FakeController,
    hvac_mode: HVACMode,
    heating: str,
    cooling: str,
) -> None:
    """Test HVAC modes map to the heating and cooling enable flags."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: hvac_mode},
        blocking=True,
    )

    await wait_for(lambda: hass.states.get(ENTITY_ID).state == hvac_mode)
    assert fake_controller.commands("setVMValue") == [
        {"dap": DAP_HK_HEATING_ENABLED, "value": heating},
        {"dap": DAP_HK_COOLING_ENABLED, "value": cooling},
    ]


@pytest.mark.parametrize(
    ("values", "action"),
    [
        (
            {DAP_HK_COOLING_ENABLED: "1", DAP_HK_HEATING_ACTIVE: "0"},
            HVACAction.IDLE,
        ),
        (
            {
                DAP_HK_COOLING_ENABLED: "1",
                DAP_HK_HEATING_ACTIVE: "0",
                DAP_HK_COOLING_ACTIVE: "1",
            },
            HVACAction.COOLING,
        ),
        ({DAP_HK_HEATING_ENABLED: "0"}, HVACAction.OFF),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_hvac_action_follows_controller(
    hass: HomeAssistant,
    fake_controller: FakeController,
    values: dict[str, str],
    action: HVACAction,
) -> None:
    """Test the HVAC action reflects the circuit state pushed by the controller."""
    await fake_controller.push(values)

    await wait_for(
        lambda: hass.states.get(ENTITY_ID).attributes[ATTR_HVAC_ACTION] == action
    )
