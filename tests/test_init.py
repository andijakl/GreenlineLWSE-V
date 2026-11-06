"""Test Greenline LWSE-V setup, unload, and connection recovery."""

from datetime import timedelta

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.greenline_lwse_v.const import (
    DAP_FLOW_RATE,
    DAP_HEAT_ENERGY_HEATING,
    DAP_HEAT_ENERGY_TOTAL,
    DAP_HEAT_OUTPUT,
    DAP_HEAT_PUMP_STATE,
    DAP_HEATING_MODE,
    DAP_HK_COOLING_ACTIVE,
    DAP_HK_COOLING_ENABLED,
    DAP_HK_CURRENT_TEMPERATURE,
    DAP_HK_HEATING_ACTIVE,
    DAP_HK_HEATING_ENABLED,
    DAP_HK_TARGET_TEMPERATURE,
    DAP_HK_TARGET_TEMPERATURE_REDUCED,
    DAP_OUTDOOR_TEMPERATURE,
    DAP_WW_CURRENT_TEMPERATURE,
    DAP_WW_TARGET_TEMPERATURE,
    DAP_WW_TARGET_TEMPERATURE_REDUCED,
    DOMAIN,
)
from homeassistant.config_entries import (
    RELOAD_AFTER_UPDATE_DELAY,
    SOURCE_REAUTH,
    ConfigEntryState,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

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


@pytest.mark.usefixtures("controller_session")
async def test_values_withheld_on_startup_are_filled_in(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    fake_controller: FakeController,
) -> None:
    """Test values the controller does not send on subscription are not lost.

    Values such as the heating mode rarely change, so without asking again they
    would stay unknown until the next change, possibly for days.
    """
    heating_mode = "sensor.greenline_lwse_v_heating_mode"
    warm_water_reduced = "number.greenline_lwse_v_warm_water_reduced_temperature"
    fake_controller.withheld = {DAP_HEATING_MODE, DAP_WW_TARGET_TEMPERATURE_REDUCED}
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    await wait_for(lambda: hass.states.get(WARM_WATER).state == "47.2")
    assert hass.states.get(heating_mode).state == STATE_UNKNOWN
    assert hass.states.get(warm_water_reduced).state == STATE_UNKNOWN

    fake_controller.withheld.clear()

    await wait_for(lambda: hass.states.get(heating_mode).state == "automatic")
    assert hass.states.get(warm_water_reduced).state == "35.0"


async def test_entities_unavailable_while_controller_is_off(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    fake_controller: FakeController,
) -> None:
    """Test a controller power cycle marks entities unavailable, then recovers."""
    await fake_controller.stop()
    await wait_for(lambda: hass.states.get(CLIMATE).state == STATE_UNAVAILABLE)
    assert hass.states.get(WARM_WATER).state == STATE_UNAVAILABLE

    fake_controller.values[DAP_WW_CURRENT_TEMPERATURE] = "45.0"
    await fake_controller.start()

    await wait_for(lambda: hass.states.get(WARM_WATER).state == "45.0")
    assert hass.states.get(CLIMATE).state == "heat"
    subscriptions = loaded_entry.runtime_data.client.subscriptions
    resubscribed = fake_controller.commands("addHotlink")[len(subscriptions) :]
    assert sorted(cmd["dap"] for cmd in resubscribed) == sorted(subscriptions)


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


@pytest.mark.usefixtures("loaded_entry")
async def test_only_enabled_entities_are_subscribed(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test the controller only receives subscriptions for enabled entities."""
    assert {cmd["dap"] for cmd in fake_controller.commands("addHotlink")} == {
        DAP_HK_HEATING_ENABLED,
        DAP_HK_HEATING_ACTIVE,
        DAP_HK_TARGET_TEMPERATURE,
        DAP_HK_CURRENT_TEMPERATURE,
        DAP_HK_COOLING_ENABLED,
        DAP_HK_COOLING_ACTIVE,
        DAP_HK_TARGET_TEMPERATURE_REDUCED,
        DAP_WW_TARGET_TEMPERATURE,
        DAP_WW_TARGET_TEMPERATURE_REDUCED,
        DAP_WW_CURRENT_TEMPERATURE,
        DAP_HEAT_PUMP_STATE,
        DAP_HEATING_MODE,
        DAP_HEAT_OUTPUT,
    }
    registry = er.async_get(hass)
    for name in (
        "outdoor_temperature",
        "flow_temperature",
        "return_temperature",
        "heat_energy",
        "heat_energy_heating",
        "heat_energy_warm_water",
        "heat_energy_cooling",
        "flow_rate",
        "compressor_starts",
        "compressor_operating_hours",
        "backup_heater_operating_hours",
    ):
        entry = registry.async_get(f"sensor.greenline_lwse_v_{name}")
        assert entry is not None, name
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entry.entity_id) is None


async def test_enabling_entities_subscribes_after_reload(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    fake_controller: FakeController,
) -> None:
    """Test enabling entities subscribes their data points on the automatic reload."""
    registry = er.async_get(hass)
    for name in ("outdoor_temperature", "heat_energy_heating"):
        registry.async_update_entity(
            f"sensor.greenline_lwse_v_{name}", disabled_by=None
        )
    assert DAP_OUTDOOR_TEMPERATURE not in loaded_entry.runtime_data.client.subscriptions

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=RELOAD_AFTER_UPDATE_DELAY + 1)
    )
    await hass.async_block_till_done()

    await wait_for(
        lambda: (
            (state := hass.states.get("sensor.greenline_lwse_v_outdoor_temperature"))
            is not None
            and state.state == "7.3"
        )
    )
    assert (
        hass.states.get("sensor.greenline_lwse_v_heat_energy_heating").state == "78065"
    )
    subscriptions = loaded_entry.runtime_data.client.subscriptions
    assert {DAP_OUTDOOR_TEMPERATURE, *DAP_HEAT_ENERGY_HEATING} <= subscriptions
    assert not {DAP_HEAT_ENERGY_TOTAL, DAP_FLOW_RATE} & subscriptions
