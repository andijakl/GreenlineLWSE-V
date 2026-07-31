"""Test the Greenline LWSE-V number entity."""

from unittest.mock import MagicMock

import pytest

from custom_components.greenline_lwse_v.const import DAP_HK_TARGET_TEMPERATURE_REDUCED
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

ENTITY_ID = "number.greenline_lwse_v_reduced_room_temperature"


@pytest.mark.usefixtures("mock_added_config_entry")
async def test_state(hass: HomeAssistant) -> None:
    """Test the number entity reflects pushed device data."""
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "17.0"


@pytest.mark.usefixtures("mock_added_config_entry")
async def test_set_value(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Test setting the reduced room temperature."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_VALUE: 16.5},
        blocking=True,
    )

    mock_client.return_value.async_set_value.assert_called_once_with(
        DAP_HK_TARGET_TEMPERATURE_REDUCED, 16.5
    )
