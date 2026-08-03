"""Constants for the Greenline LWSE-V integration."""

DOMAIN = "greenline_lwse_v"

MANUFACTURER = "NIBE"
MODEL = "Greenline LWSE-V"

PORT = 3118

_HK_ID = 1
_WW_ID = 1

DAP_HK_HEATING_ENABLED = f"1.100.{_HK_ID}.2"
DAP_HK_HEATING_ACTIVE = f"1.100.{_HK_ID}.3"
DAP_HK_TARGET_TEMPERATURE = f"1.100.{_HK_ID}.5"
DAP_HK_TARGET_TEMPERATURE_REDUCED = f"1.100.{_HK_ID}.6"
DAP_HK_CURRENT_TEMPERATURE = f"1.100.{_HK_ID}.100"
DAP_HK_COOLING_ENABLED = f"1.100.{_HK_ID}.201"
DAP_HK_COOLING_ACTIVE = f"1.100.{_HK_ID}.202"

DAP_WW_TARGET_TEMPERATURE = f"1.101.{_WW_ID}.5"
DAP_WW_CURRENT_TEMPERATURE = f"1.101.{_WW_ID}.20"

SUBSCRIBED_DAPS = (
    DAP_HK_HEATING_ENABLED,
    DAP_HK_HEATING_ACTIVE,
    DAP_HK_TARGET_TEMPERATURE,
    DAP_HK_TARGET_TEMPERATURE_REDUCED,
    DAP_HK_CURRENT_TEMPERATURE,
    DAP_HK_COOLING_ENABLED,
    DAP_HK_COOLING_ACTIVE,
    DAP_WW_TARGET_TEMPERATURE,
    DAP_WW_CURRENT_TEMPERATURE,
)

TEMPERATURE_MIN = 0
TEMPERATURE_MAX = 40


def is_legacy_mac_device_id(device_id: str) -> bool:
    """Return whether an entry uses the legacy colon-separated MAC identifier."""
    parts = device_id.split(":")
    return len(parts) == 6 and all(
        len(part) == 2
        and all(character in "0123456789abcdef" for character in part.lower())
        for part in parts
    )
