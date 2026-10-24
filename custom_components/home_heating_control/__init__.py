"""Home Heating Control: Heizungssteuerung mit Zonen für Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .controller import HeatingController

PLATFORMS = ["sensor", "switch", "number"]

type HeatingConfigEntry = ConfigEntry[HeatingController]


async def async_setup_entry(hass: HomeAssistant, entry: HeatingConfigEntry) -> bool:
    """Integration einrichten: Controller anlegen, Entitäten laden, Auslöser starten."""
    controller = HeatingController(hass, entry)
    entry.runtime_data = controller
    _register_devices(hass, entry, controller)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await controller.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HeatingConfigEntry) -> bool:
    """Integration entladen."""
    entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: HeatingConfigEntry) -> None:
    """Bei geänderten Einstellungen oder Zonen neu laden."""
    if entry.runtime_data.skip_reload:
        # Änderung kam vom ECO-Regler, der Controller kennt den Wert schon.
        entry.runtime_data.skip_reload = False
        return
    await hass.config_entries.async_reload(entry.entry_id)


def _register_devices(
    hass: HomeAssistant, entry: HeatingConfigEntry, controller: HeatingController
) -> None:
    """Geräte vor den Entitäten anlegen: ein Hauptgerät und je Zone ein Gerät darunter."""
    registry = dr.async_get(hass)
    main = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Home Heating Control",
    )
    for subentry_id, zone in controller.zones.items():
        device = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=subentry_id,
            identifiers={(DOMAIN, subentry_id)},
            name=zone.name,
        )
        registry.async_update_device(device.id, via_device_id=main.id)
