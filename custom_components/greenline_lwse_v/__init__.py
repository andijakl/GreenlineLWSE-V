"""The Greenline LWSE-V integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN
from .coordinator import GreenlineLWSEConfigEntry, GreenlineLWSECoordinator

_PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.NUMBER, Platform.SENSOR]
_ENTITY_UNIQUE_ID_SUFFIXES: tuple[tuple[Platform, str], ...] = (
    (Platform.CLIMATE, "_hk1"),
    (Platform.NUMBER, "_hk1_reduced_temperature"),
    (Platform.SENSOR, "_warm_water_temperature"),
    (Platform.SENSOR, "_warm_water_target_temperature"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: GreenlineLWSEConfigEntry
) -> bool:
    """Set up Greenline LWSE-V from a config entry."""
    coordinator = GreenlineLWSECoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    if (
        coordinator.controller_serial is not None
        and coordinator.controller_serial != coordinator.device_id
    ):
        _migrate_legacy_identity(
            hass, entry, coordinator.device_id, coordinator.controller_serial
        )
        coordinator.device_id = coordinator.controller_serial

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


def _migrate_legacy_identity(
    hass: HomeAssistant,
    entry: GreenlineLWSEConfigEntry,
    old_device_id: str,
    controller_serial: str,
) -> None:
    """Migrate a MAC-based entry and registry records to the controller serial."""
    entity_registry = er.async_get(hass)
    for platform, suffix in _ENTITY_UNIQUE_ID_SUFFIXES:
        entity_id = entity_registry.async_get_entity_id(
            platform, DOMAIN, f"{old_device_id}{suffix}"
        )
        if entity_id is not None:
            entity_registry.async_update_entity(
                entity_id, new_unique_id=f"{controller_serial}{suffix}"
            )

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, old_device_id)})
    if device is not None:
        device_registry.async_update_device(
            device.id,
            new_identifiers={(DOMAIN, controller_serial)},
            serial_number=controller_serial,
        )

    hass.config_entries.async_update_entry(entry, unique_id=controller_serial)
