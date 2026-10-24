"""Gemeinsame Basis der Entitäten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, signal_update
from .controller import HeatingController


def global_device(controller: HeatingController) -> DeviceInfo:
    """Gerät für die globalen Schalter."""
    return DeviceInfo(identifiers={(DOMAIN, controller.entry.entry_id)})


def zone_device(controller: HeatingController, subentry_id: str) -> DeviceInfo:
    """Gerät einer Zone."""
    return DeviceInfo(identifiers={(DOMAIN, subentry_id)})


class HeatingEntity(Entity):
    """Basisklasse: kennt den Controller und aktualisiert sich bei neuen Entscheidungen."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: HeatingController) -> None:
        self.controller = controller

    async def async_added_to_hass(self) -> None:
        """Auf Neuberechnungen des Controllers hören."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_update(self.controller.entry.entry_id),
                self.async_write_ha_state,
            )
        )
