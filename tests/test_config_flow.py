"""Test the Greenline LWSE-V config flow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenline_lwse_v.api import (
    GreenlineLWSEAuthError,
    GreenlineLWSEConnectionError,
)
from custom_components.greenline_lwse_v.const import DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import TEST_DEVICE_ID, TEST_HOST, TEST_PASSWORD, TEST_USERNAME

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

USER_INPUT = {
    CONF_HOST: TEST_HOST,
    CONF_USERNAME: TEST_USERNAME,
    CONF_PASSWORD: TEST_PASSWORD,
}


@pytest.fixture
def mock_validate_input() -> Generator[MagicMock]:
    """Mock a successful config-flow connection attempt."""
    with patch(
        "custom_components.greenline_lwse_v.config_flow.GreenlineLWSEClient",
        autospec=True,
    ) as mock_client_cls:
        client = mock_client_cls.return_value
        client.async_connect = AsyncMock(return_value=TEST_DEVICE_ID)
        client.async_disconnect = AsyncMock()
        yield client


async def test_form(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_validate_input: MagicMock,
) -> None:
    """Test the form creates a serial-identified config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: f"http://{TEST_HOST}/"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NIBE Greenline LWSE-V"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == TEST_DEVICE_ID
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        pytest.param(GreenlineLWSEAuthError("nope"), "invalid_auth", id="auth"),
        pytest.param(
            GreenlineLWSEConnectionError("nope"), "cannot_connect", id="connection"
        ),
        pytest.param(RuntimeError("boom"), "unknown", id="unexpected"),
    ],
)
async def test_form_errors(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_validate_input: MagicMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Test validation errors and successful retry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    mock_validate_input.async_connect.side_effect = side_effect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_validate_input.async_connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_already_configured(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_validate_input: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the flow aborts for an existing controller serial."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_validate_input: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the reauthentication flow updates credentials."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    mock_validate_input.async_connect.side_effect = GreenlineLWSEAuthError("nope")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**USER_INPUT, CONF_PASSWORD: "new-password"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    mock_validate_input.async_connect.side_effect = None
    mock_validate_input.async_connect.return_value = "different-controller"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**USER_INPUT, CONF_PASSWORD: "new-password"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "wrong_device"}

    mock_validate_input.async_connect.return_value = TEST_DEVICE_ID
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**USER_INPUT, CONF_PASSWORD: "new-password"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-password"
