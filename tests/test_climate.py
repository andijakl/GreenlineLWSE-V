"""Test the Greenline LWSE-V climate entity."""

from unittest.mock import MagicMock

import pytest

from custom_components.greenline_lwse_v.const import (
    DAP_HK_COOLING_ENABLED,
    DAP_HK_HEATING_ENABLED,
    DAP_HK_TARGET_TEMPERATURE,
    DOMAIN,
)
from homeassistant.components.climate import (
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

from .conftest import TEST_MAC

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

ENTITY_ID = "climate.greenline_lwse_v"


@pytest.mark.usefixtures("mock_added_config_entry")
async def test_state_and_stable_identifiers(hass: HomeAssistant) -> None:
    """Test the climate state and MAC-backed identifiers."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.HEATING
    assert state.attributes[ATTR_TEMPERATURE] == 21.0
    assert state.attributes["current_temperature"] == 20.5

    entity_entry = er.async_get(hass).async_get(ENTITY_ID)
    assert entity_entry.unique_id == f"{TEST_MAC}_hk1"
    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, TEST_MAC)})


@pytest.mark.usefixtures("mock_added_config_entry")
async def test_set_temperature(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test setting the target temperature."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 22.5},
        blocking=True,
    )

    mock_client.return_value.async_set_value.assert_called_once_with(
        DAP_HK_TARGET_TEMPERATURE, 22.5
    )


@pytest.mark.usefixtures("mock_added_config_entry")
async def test_set_hvac_mode(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test enabling both heating and cooling."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.HEAT_COOL},
        blocking=True,
    )

    mock_client.return_value.async_set_value.assert_any_call(
        DAP_HK_HEATING_ENABLED, "1"
    )
    mock_client.return_value.async_set_value.assert_any_call(
        DAP_HK_COOLING_ENABLED, "1"
    )
