"""The Greenline LWSE-V integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import GreenlineLWSEConfigEntry, GreenlineLWSECoordinator

_PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.NUMBER, Platform.SENSOR]
# Entities replaced by another platform; removed so they do not linger as unavailable.
_REPLACED_ENTITY_UNIQUE_ID_SUFFIXES: tuple[tuple[Platform, str], ...] = (
    (Platform.SENSOR, "_warm_water_target_temperature"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: GreenlineLWSEConfigEntry
) -> bool:
    """Set up Greenline LWSE-V from a config entry."""
    coordinator = GreenlineLWSECoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    _remove_replaced_entities(hass, coordinator.device_id)
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


def _remove_replaced_entities(hass: HomeAssistant, device_id: str) -> None:
    """Remove registry entries of entities that moved to another platform."""
    entity_registry = er.async_get(hass)
    for platform, suffix in _REPLACED_ENTITY_UNIQUE_ID_SUFFIXES:
        entity_id = entity_registry.async_get_entity_id(
            platform, DOMAIN, f"{device_id}{suffix}"
        )
        if entity_id is not None:
            entity_registry.async_remove(entity_id)
