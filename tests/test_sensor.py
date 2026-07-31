"""Test Greenline LWSE-V sensor entities."""

import pytest

from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.mark.usefixtures("mock_added_config_entry")
async def test_state(hass: HomeAssistant) -> None:
    """Test warm-water sensors reflect pushed device data."""
    state = hass.states.get("sensor.greenline_lwse_v_warm_water_temperature")
    assert state is not None
    assert state.state == "47.2"

    state = hass.states.get("sensor.greenline_lwse_v_warm_water_target_temperature")
    assert state is not None
    assert state.state == "48.0"
