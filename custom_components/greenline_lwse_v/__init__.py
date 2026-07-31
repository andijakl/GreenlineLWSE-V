"""The Greenline LWSE-V integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import GreenlineLWSEConfigEntry, GreenlineLWSECoordinator

_PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.NUMBER, Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: GreenlineLWSEConfigEntry
) -> bool:
    """Set up Greenline LWSE-V from a config entry."""
    coordinator = GreenlineLWSECoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GreenlineLWSEConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_disconnect()
    return unload_ok
