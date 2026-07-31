"""Test Greenline LWSE-V integration setup."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenline_lwse_v.api import (
    GreenlineLWSEAuthError,
    GreenlineLWSEConnectionError,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Test successful setup and unload of a config entry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    client = mock_client.return_value
    client.async_connect.assert_called_once()
    client.async_run.assert_called_once()

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    client.async_disconnect.assert_called_once()


async def test_setup_entry_cannot_connect(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Test setup retries when the device cannot be reached."""
    mock_client.return_value.async_connect.side_effect = GreenlineLWSEConnectionError(
        "nope"
    )
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_auth_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Test setup starts reauthentication after invalid credentials."""
    mock_client.return_value.async_connect.side_effect = GreenlineLWSEAuthError("nope")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(mock_config_entry.domain)
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


@pytest.mark.usefixtures("mock_added_config_entry")
async def test_runtime_auth_failure_starts_reauth(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Test a runtime authentication failure starts reauthentication."""
    on_connection_lost = mock_client.call_args.kwargs["on_connection_lost"]
    on_connection_lost(GreenlineLWSEAuthError("nope"))
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler("greenline_lwse_v")
    assert any(flow["context"]["source"] == "reauth" for flow in flows)
