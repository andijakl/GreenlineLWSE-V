"""Common fixtures for Greenline tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

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
    DOMAIN,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

TEST_HOST = "192.168.20.1"
TEST_USERNAME = "homeassistant"
TEST_PASSWORD = "test-password"
TEST_MAC = "aa:bb:cc:dd:ee:ff"

TEST_DATA = {
    DAP_HK_HEATING_ENABLED: "1",
    DAP_HK_HEATING_ACTIVE: "1",
    DAP_HK_TARGET_TEMPERATURE: "21.0",
    DAP_HK_TARGET_TEMPERATURE_REDUCED: "17.0",
    DAP_HK_CURRENT_TEMPERATURE: "20.5",
    DAP_HK_COOLING_ENABLED: "0",
    DAP_HK_COOLING_ACTIVE: "0",
    DAP_WW_TARGET_TEMPERATURE: "48.0",
    DAP_WW_CURRENT_TEMPERATURE: "47.2",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: object) -> None:
    """Enable loading the integration from custom_components in every test."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "custom_components.greenline_lwse_v.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_get_mac_address() -> Generator[MagicMock]:
    """Mock the MAC address lookup used by the config flow."""
    with patch(
        "custom_components.greenline_lwse_v.config_flow.get_mac_address",
        return_value=TEST_MAC,
    ) as mock_get_mac:
        yield mock_get_mac


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a Greenline mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_MAC,
        data={
            CONF_HOST: TEST_HOST,
            CONF_USERNAME: TEST_USERNAME,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Mock the client created by the coordinator."""
    with patch(
        "custom_components.greenline_lwse_v.coordinator.GreenlineLWSEClient",
        autospec=True,
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.async_connect = AsyncMock()
        client.async_disconnect = AsyncMock()
        client.async_subscribe = AsyncMock()
        client.async_set_value = AsyncMock()
        client.async_run = AsyncMock()
        yield mock_client_cls


@pytest.fixture
async def mock_added_config_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> MockConfigEntry:
    """Set up the integration with pushed device data."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    on_data = mock_client.call_args.kwargs["on_data"]
    on_data(TEST_DATA)
    await hass.async_block_till_done()

    return mock_config_entry
