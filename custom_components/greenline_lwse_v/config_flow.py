"""Config flow for the Greenline LWSE-V integration."""

from collections.abc import Mapping
import logging
from typing import Any, override
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    GreenlineLWSEAuthError,
    GreenlineLWSEClient,
    GreenlineLWSEConnectionError,
)
from .const import DOMAIN, is_legacy_mac_device_id

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """Validate connection details and return the controller serial."""
    client = GreenlineLWSEClient(
        session=async_get_clientsession(hass),
        host=data[CONF_HOST],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        on_data=lambda _values: None,
        on_connection_lost=lambda _err: None,
    )
    try:
        return await client.async_connect()
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
            errors, device_id = await self._async_validate(user_input)
            if not errors:
                if device_id is None:
                    raise RuntimeError("Validated controller has no serial")
                if self.source == SOURCE_REAUTH:
                    reauth_entry = self._get_reauth_entry()
                    if (
                        device_id != reauth_entry.unique_id
                        and reauth_entry.unique_id is not None
                        and not is_legacy_mac_device_id(reauth_entry.unique_id)
                    ):
                        errors["base"] = "wrong_device"
                    else:
                        return self.async_update_reload_and_abort(
                            reauth_entry, data=user_input
                        )
                else:
                    await self.async_set_unique_id(device_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="NIBE Greenline LWSE-V", data=user_input
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

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, str], str | None]:
        """Validate user input and return flow errors plus the device identifier."""
        errors: dict[str, str] = {}
        device_id: str | None = None
        try:
            user_input[CONF_HOST] = _normalize_host(user_input[CONF_HOST])
        except ValueError:
            errors["base"] = "cannot_connect"
            return errors, device_id

        try:
            device_id = await validate_input(self.hass, user_input)
        except GreenlineLWSEAuthError:
            errors["base"] = "invalid_auth"
        except GreenlineLWSEConnectionError as err:
            _LOGGER.warning(
                "Could not connect to Greenline LWSE-V at %s: %s",
                user_input[CONF_HOST],
                err,
            )
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        return errors, device_id


def _normalize_host(value: str) -> str:
    """Extract a bare host from an IP, hostname, or controller URL."""
    value = value.strip()
    parsed = urlsplit(value if "://" in value else f"//{value}")
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        raise ValueError("Unsupported controller URL scheme")
    if parsed.hostname is None:
        raise ValueError("Controller host is missing")
    return parsed.hostname
