"""Common fixtures for Greenline tests."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenline_lwse_v.const import (
    DAP_HK_COOLING_ACTIVE,
    DAP_HK_COOLING_ENABLED,
    DAP_HK_CURRENT_TEMPERATURE,
    DAP_HK_HEATING_ACTIVE,
    DAP_HK_HEATING_ENABLED,
    DAP_HK_TARGET_TEMPERATURE,
    DAP_HK_TARGET_TEMPERATURE_REDUCED,
    DAP_WW_CURRENT_TEMPERATURE,
    DAP_WW_TARGET_TEMPERATURE,
    DAP_WW_TARGET_TEMPERATURE_REDUCED,
    DOMAIN,
    SUBSCRIBED_DAPS,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.util.async_ import get_scheduled_timer_handles

from .fake_controller import (
    CONTROLLER_HOST,
    FakeController,
    FakeControllerResolver,
    wait_for,
)

TEST_HOST = CONTROLLER_HOST
TEST_USERNAME = "homeassistant"
TEST_PASSWORD = "test-password"
TEST_DEVICE_ID = "120617430000044"

TEST_DATA = {
    DAP_HK_HEATING_ENABLED: "1",
    DAP_HK_HEATING_ACTIVE: "1",
    DAP_HK_TARGET_TEMPERATURE: "21.0",
    DAP_HK_TARGET_TEMPERATURE_REDUCED: "17.0",
    DAP_HK_CURRENT_TEMPERATURE: "20.5",
    DAP_HK_COOLING_ENABLED: "0",
    DAP_HK_COOLING_ACTIVE: "0",
    DAP_WW_TARGET_TEMPERATURE: "48.0",
    DAP_WW_TARGET_TEMPERATURE_REDUCED: "35.0",
    DAP_WW_CURRENT_TEMPERATURE: "47.2",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: object) -> None:
    """Enable loading the integration from custom_components in every test."""


@pytest.fixture
async def mock_setup_entry(hass: HomeAssistant) -> AsyncGenerator[AsyncMock]:
    """Override setting up and unloading entries created by config flow tests.

    The entries are unloaded while the override is active; otherwise the test
    harness would unload them with the real unload function, which expects a
    connection that a mocked setup never created.
    """
    with (
        patch(
            "custom_components.greenline_lwse_v.async_setup_entry", return_value=True
        ) as mock_setup,
        patch(
            "custom_components.greenline_lwse_v.async_unload_entry", return_value=True
        ),
    ):
        yield mock_setup
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                await hass.config_entries.async_unload(entry.entry_id)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a Greenline mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_DEVICE_ID,
        data={
            CONF_HOST: TEST_HOST,
            CONF_USERNAME: TEST_USERNAME,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )


@pytest.fixture
async def fake_controller(socket_enabled: None) -> AsyncGenerator[FakeController]:
    """Run a fake controller on a local socket."""
    controller = FakeController(
        serial=TEST_DEVICE_ID,
        username=TEST_USERNAME,
        password=TEST_PASSWORD,
        values=TEST_DATA,
    )
    await controller.start()
    yield controller
    await controller.stop()


@pytest.fixture
async def controller_session(
    hass: HomeAssistant, fake_controller: FakeController
) -> AsyncGenerator[aiohttp.ClientSession]:
    """Route the integration's HTTP and WebSocket traffic to the fake controller.

    Reconnect and login delays are shortened so recovery scenarios run quickly.
    """
    session = aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(resolver=FakeControllerResolver(fake_controller))
    )
    with (
        patch(
            "custom_components.greenline_lwse_v.coordinator.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.greenline_lwse_v.config_flow.async_get_clientsession",
            return_value=session,
        ),
        patch("custom_components.greenline_lwse_v.api.RECONNECT_DELAY", 0.05),
        patch("custom_components.greenline_lwse_v.api.LOGIN_TIMEOUT", 1),
    ):
        yield session
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is ConfigEntryState.LOADED:
                await hass.config_entries.async_unload(entry.entry_id)
    await session.close()
    _cancel_closed_websocket_heartbeats(hass)


def _cancel_closed_websocket_heartbeats(hass: HomeAssistant) -> None:
    """Cancel heartbeat timers that aiohttp re-arms after a WebSocket closed.

    aiohttp 3.14 reschedules the heartbeat when the peer's close frame arrives
    during close(). The timer is harmless (its ping on the closed socket is
    ignored), but would fail the lingering-timer check. Heartbeats of WebSockets
    that are still open are left alone, so real leaks are still reported.
    """
    for handle in get_scheduled_timer_handles(hass.loop):
        websocket = getattr(handle._callback, "__self__", None)
        if isinstance(websocket, aiohttp.ClientWebSocketResponse) and websocket.closed:
            handle.cancel()


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    controller_session: aiohttp.ClientSession,
) -> MockConfigEntry:
    """Set up the integration against the fake controller with all values received."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = mock_config_entry.runtime_data
    await wait_for(lambda: all(dap in coordinator.data for dap in SUBSCRIBED_DAPS))
    await hass.async_block_till_done()
    return mock_config_entry
