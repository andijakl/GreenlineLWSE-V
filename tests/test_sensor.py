"""Test Greenline LWSE-V sensor entities."""

import pytest

from custom_components.greenline_lwse_v.const import DAP_WW_CURRENT_TEMPERATURE
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .fake_controller import FakeController, wait_for

ENTITY_ID = "sensor.greenline_lwse_v_warm_water_temperature"


@pytest.mark.usefixtures("loaded_entry")
async def test_state_follows_controller(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test the warm-water temperature follows controller pushes."""
    assert hass.states.get(ENTITY_ID).state == "47.2"

    await fake_controller.push({DAP_WW_CURRENT_TEMPERATURE: "46.8"})
    await wait_for(lambda: hass.states.get(ENTITY_ID).state == "46.8")

    await fake_controller.push({DAP_WW_CURRENT_TEMPERATURE: "---"})
    await wait_for(lambda: hass.states.get(ENTITY_ID).state == STATE_UNKNOWN)
