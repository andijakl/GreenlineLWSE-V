"""Test the Greenline LWSE-V number entities."""

import pytest

from custom_components.greenline_lwse_v.const import (
    DAP_HK_TARGET_TEMPERATURE_REDUCED,
    DAP_WW_TARGET_TEMPERATURE,
    DAP_WW_TARGET_TEMPERATURE_REDUCED,
)
from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .fake_controller import FakeController, wait_for

HK_REDUCED = "number.greenline_lwse_v_reduced_room_temperature"
WW_TARGET = "number.greenline_lwse_v_warm_water_target_temperature"
WW_REDUCED = "number.greenline_lwse_v_warm_water_reduced_temperature"


@pytest.mark.parametrize(
    ("entity_id", "state", "maximum"),
    [(HK_REDUCED, "17.0", 40), (WW_TARGET, "48.0", 99), (WW_REDUCED, "35.0", 99)],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_state(
    hass: HomeAssistant, entity_id: str, state: str, maximum: float
) -> None:
    """Test the number entities reflect controller values and limits."""
    entity_state = hass.states.get(entity_id)
    assert entity_state is not None
    assert entity_state.state == state
    assert entity_state.attributes[ATTR_MIN] == 0
    assert entity_state.attributes[ATTR_MAX] == maximum
    assert entity_state.attributes[ATTR_STEP] == 0.1


@pytest.mark.parametrize(
    ("entity_id", "dap", "value"),
    [
        (HK_REDUCED, DAP_HK_TARGET_TEMPERATURE_REDUCED, 16.5),
        (WW_TARGET, DAP_WW_TARGET_TEMPERATURE, 50.5),
        (WW_REDUCED, DAP_WW_TARGET_TEMPERATURE_REDUCED, 32.5),
    ],
)
@pytest.mark.usefixtures("loaded_entry")
async def test_set_value(
    hass: HomeAssistant,
    fake_controller: FakeController,
    entity_id: str,
    dap: str,
    value: float,
) -> None:
    """Test a setpoint is written to its data point and confirmed by the controller."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )

    await wait_for(lambda: hass.states.get(entity_id).state == str(value))
    assert fake_controller.commands("setVMValue") == [{"dap": dap, "value": str(value)}]


@pytest.mark.usefixtures("loaded_entry")
async def test_set_value_outside_limits_is_rejected(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test out-of-range setpoints never reach the controller."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: HK_REDUCED, ATTR_VALUE: 45},
            blocking=True,
        )

    assert not fake_controller.commands("setVMValue")
