"""Test the Greenline LWSE-V config flow against a fake controller."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.greenline_lwse_v.const import DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import TEST_DEVICE_ID, TEST_HOST, TEST_PASSWORD, TEST_USERNAME
from .fake_controller import FakeController, wait_for

pytestmark = pytest.mark.usefixtures("controller_session", "mock_setup_entry")

USER_INPUT = {
    CONF_HOST: TEST_HOST,
    CONF_USERNAME: TEST_USERNAME,
    CONF_PASSWORD: TEST_PASSWORD,
}


async def _start_user_flow(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}
    return result["flow_id"]


async def test_form_creates_entry_from_web_interface_url(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test a URL copied from the browser creates a serial-identified entry."""
    flow_id = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {**USER_INPUT, CONF_HOST: f" http://{TEST_HOST}/#!/home "}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NIBE Greenline LWSE-V"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == TEST_DEVICE_ID
    assert fake_controller.login_count == 1
    await wait_for(lambda: fake_controller.connection_count == 0)


@pytest.mark.parametrize(
    ("host", "error"),
    [
        pytest.param(TEST_HOST, "invalid_auth", id="wrong-password"),
        pytest.param("ftp://greenline.test", "cannot_connect", id="unsupported-url"),
        pytest.param("http://", "cannot_connect", id="missing-host"),
        pytest.param("unknown-host.test", "cannot_connect", id="unknown-host"),
    ],
)
async def test_form_errors_then_success(
    hass: HomeAssistant, fake_controller: FakeController, host: str, error: str
) -> None:
    """Test input mistakes show an error and the user can correct them."""
    flow_id = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {**USER_INPUT, CONF_HOST: host, CONF_PASSWORD: "wrong-password"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    result = await hass.config_entries.flow.async_configure(flow_id, USER_INPUT)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    await wait_for(lambda: fake_controller.connection_count == 0)


async def test_form_controller_offline(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    """Test setting up while the controller is switched off."""
    await fake_controller.stop()
    flow_id = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(flow_id, USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_unexpected_error(hass: HomeAssistant) -> None:
    """Test an unexpected client failure is reported instead of crashing the flow."""
    flow_id = await _start_user_flow(hass)

    with patch(
        "custom_components.greenline_lwse_v.config_flow.validate_input",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await hass.config_entries.flow.async_configure(flow_id, USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.usefixtures("fake_controller")
async def test_form_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test the same controller cannot be added twice, even under another name."""
    mock_config_entry.add_to_hass(hass)
    flow_id = await _start_user_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id, {**USER_INPUT, CONF_HOST: f"http://{TEST_HOST}"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant,
    fake_controller: FakeController,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test reauthentication after the controller password was changed."""
    mock_config_entry.add_to_hass(hass)
    fake_controller.password = "new-password"

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    fake_controller.serial = "999999999999999"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "wrong_device"}

    fake_controller.serial = TEST_DEVICE_ID
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_PASSWORD: "new-password"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-password"
    assert mock_setup_entry.call_count == 1
