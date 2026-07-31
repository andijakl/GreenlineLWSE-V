"""Config flow for the Greenline LWSE-V integration."""

from collections.abc import Mapping
from functools import partial
import logging
from typing import Any, override

from getmac import get_mac_address
import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    GreenlineLWSEAuthError,
    GreenlineLWSEClient,
    GreenlineLWSEConnectionError,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate connection and authentication details."""
    client = GreenlineLWSEClient(
        session=async_get_clientsession(hass),
        host=data[CONF_HOST],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        on_data=lambda _values: None,
        on_connection_lost=lambda _err: None,
    )
    try:
        await client.async_connect()
    finally:
        await client.async_disconnect()


class GreenlineLWSEConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Greenline LWSE-V."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial and reauthentication forms."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate(user_input)
            if not errors:
                if self.source == SOURCE_REAUTH:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data=user_input
                    )
                mac = await _async_get_mac_address(self.hass, user_input[CONF_HOST])
                if mac is None:
                    errors["base"] = "mac_unavailable"
                else:
                    await self.async_set_unique_id(mac)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="Greenline LWSE-V", data=user_input
                    )

        schema = self.add_suggested_values_to_schema(
            STEP_USER_DATA_SCHEMA,
            user_input
            or (
                self._get_reauth_entry().data if self.source == SOURCE_REAUTH else None
            ),
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication."""
        return await self.async_step_user()

    async def _async_validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Validate user input and return flow errors."""
        errors: dict[str, str] = {}
        try:
            await validate_input(self.hass, user_input)
        except GreenlineLWSEAuthError:
            errors["base"] = "invalid_auth"
        except GreenlineLWSEConnectionError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        return errors


async def _async_get_mac_address(hass: HomeAssistant, host: str) -> str | None:
    """Look up the device MAC address for its stable identifier."""
    mac_address = await hass.async_add_executor_job(partial(get_mac_address, ip=host))
    if not mac_address:
        return None
    return dr.format_mac(mac_address)
