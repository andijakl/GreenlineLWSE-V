"""Data update coordinator for the Greenline LWSE-V integration."""

import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    GreenlineLWSEAuthError,
    GreenlineLWSEClient,
    GreenlineLWSEConnectionError,
)
from .const import DOMAIN, SUBSCRIBED_DAPS, is_legacy_mac_device_id

_LOGGER = logging.getLogger(__name__)

type GreenlineLWSEConfigEntry = ConfigEntry[GreenlineLWSECoordinator]


class GreenlineLWSECoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Keep the latest values pushed by the device."""

    config_entry: GreenlineLWSEConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: GreenlineLWSEConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=None,
        )
        if (device_id := config_entry.unique_id) is None:
            raise ValueError("Greenline LWSE-V config entry has no device identifier")
        self.device_id = device_id
        self.controller_serial: str | None = None
        self.data = {}
        self.client = GreenlineLWSEClient(
            session=async_get_clientsession(hass),
            host=config_entry.data[CONF_HOST],
            username=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            on_data=self._handle_data,
            on_connection_lost=self._handle_connection_lost,
        )

    def _handle_data(self, values: dict[str, str]) -> None:
        """Handle values pushed by the device."""
        self.async_set_updated_data({**self.data, **values})

    def _handle_connection_lost(self, err: Exception) -> None:
        """Handle a connection loss reported by the protocol client."""
        if isinstance(err, GreenlineLWSEAuthError):
            self.config_entry.async_start_reauth(self.hass)
        self.async_set_update_error(err)

    @override
    async def _async_update_data(self) -> dict[str, str]:
        """Connect to the device and subscribe to required data points."""
        try:
            serial = await self.client.async_connect()
        except GreenlineLWSEAuthError as err:
            raise ConfigEntryAuthFailed from err
        except GreenlineLWSEConnectionError as err:
            raise UpdateFailed(str(err)) from err

        if serial != self.device_id and not is_legacy_mac_device_id(self.device_id):
            await self.client.async_disconnect()
            raise UpdateFailed(
                "Connected controller does not match the configured device"
            )

        self.controller_serial = serial
        try:
            for dap in SUBSCRIBED_DAPS:
                await self.client.async_subscribe(dap)
        except GreenlineLWSEConnectionError as err:
            await self.client.async_disconnect()
            raise UpdateFailed(str(err)) from err

        self.config_entry.async_create_background_task(
            self.hass, self.client.async_run(), f"{DOMAIN}-connection"
        )
        return self.data
