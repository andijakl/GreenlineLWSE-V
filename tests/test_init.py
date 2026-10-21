"""Test Greenline LWSE-V setup, unload, and connection recovery."""

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenline_lwse_v.const import (
    DAP_WW_CURRENT_TEMPERATURE,
    DOMAIN,
    SUBSCRIBED_DAPS,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import TEST_DEVICE_ID
from .fake_controller import FakeController, wait_for

CLIMATE = "climate.greenline_lwse_v"
WARM_WATER = "sensor.greenline_lwse_v_warm_water_temperature"


def _reauth_in_progress(hass: HomeAssistant) -> bool:
    return any(
        flow["context"]["source"] == SOURCE_REAUTH
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    )


async def test_setup_and_unload(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    fake_controller: FakeController,
) -> None:
    """Test setup registers the controller and unload closes its connection."""
    assert loaded_entry.state is ConfigEntryState.LOADED
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, TEST_DEVICE_ID), loaded_entry.entry_id
    )
    assert device is not None
    assert device.serial_number == TEST_DEVICE_ID
    assert fake_controller.connection_count == 1

    await hass.config_entries.async_unload(loaded_entry.entry_id)
    await hass.async_block_till_done()

    assert loaded_entry.state is ConfigEntryState.NOT_LOADED
    await wait_for(lambda: fake_controller.connection_count == 0)
    assert fake_controller.login_count == 1


@pytest.mark.usefixtures("controller_session")
async def test_setup_retries_until_controller_is_online(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    fake_controller: FakeController,
) -> None:
    """Test Home Assistant starting before the heat pump controller."""
    await fake_controller.stop()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY

    await fake_controller.start()
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    await wait_for(lambda: hass.states.get(WARM_WATER).state == "47.2")


@pytest.mark.usefixtures("controller_session")
async def test_setup_with_changed_password_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    fake_controller: FakeController,
) -> None:
    """Test setup after the controller password was changed."""
    fake_controller.password = "changed-on-controller"
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert _reauth_in_progress(hass)


@pytest.mark.usefixtures("controller_session")
async def test_setup_rejects_a_different_controller(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    fake_controller: FakeController,
) -> None:
    """Test the entry does not attach to another controller at the same address."""
    fake_controller.serial = "999999999999999"
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not fake_controller.commands("addHotlink")
    await wait_for(lambda: fake_controller.connection_count == 0)


@pytest.mark.usefixtures("loaded_entry")
async def test_entities_unavailable_while_controller_is_off(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test a controller power cycle marks entities unavailable, then recovers."""
    await fake_controller.stop()
    await wait_for(lambda: hass.states.get(CLIMATE).state == STATE_UNAVAILABLE)
    assert hass.states.get(WARM_WATER).state == STATE_UNAVAILABLE

    fake_controller.values[DAP_WW_CURRENT_TEMPERATURE] = "45.0"
    await fake_controller.start()

    await wait_for(lambda: hass.states.get(WARM_WATER).state == "45.0")
    assert hass.states.get(CLIMATE).state == "heat"
    resubscribed = fake_controller.commands("addHotlink")[len(SUBSCRIBED_DAPS) :]
    assert sorted(cmd["dap"] for cmd in resubscribed) == sorted(SUBSCRIBED_DAPS)


@pytest.mark.usefixtures("loaded_entry")
async def test_password_change_at_runtime_starts_reauth(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test changed credentials during operation ask the user to reauthenticate."""
    fake_controller.password = "changed-on-controller"

    await fake_controller.drop_connections()

    await wait_for(lambda: _reauth_in_progress(hass))
    assert hass.states.get(CLIMATE).state == STATE_UNAVAILABLE
    assert fake_controller.login_count == 2


async def test_setup_removes_replaced_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    controller_session: aiohttp.ClientSession,
) -> None:
    """Test the former warm-water target sensor is removed from the registry."""
    mock_config_entry.add_to_hass(hass)
    entity_registry = er.async_get(hass)
    old_sensor = entity_registry.async_get_or_create(
        Platform.SENSOR,
        DOMAIN,
        f"{TEST_DEVICE_ID}_warm_water_target_temperature",
        config_entry=mock_config_entry,
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get(old_sensor.entity_id) is None
    assert entity_registry.async_get_entity_id(
        Platform.NUMBER, DOMAIN, f"{TEST_DEVICE_ID}_warm_water_target_temperature"
    )
