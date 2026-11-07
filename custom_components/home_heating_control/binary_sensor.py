"""Pro Zone ein Problem-Sensor (Thermostat weg, Befehl abgelehnt, Fenster lange offen)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatingConfigEntry
from .controller import HeatingController
from .entity import HeatingEntity, zone_device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Problem-Sensor je Zone anlegen."""
    controller = entry.runtime_data
    for subentry_id in controller.zones:
        async_add_entities(
            [ZoneProblemSensor(controller, subentry_id)],
            config_subentry_id=subentry_id,
        )


class ZoneProblemSensor(HeatingEntity, BinarySensorEntity):
    """An, solange die Zone ein Problem hat; die Arten stehen im Attribut `problems`."""

    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller: HeatingController, subentry_id: str) -> None:
        super().__init__(controller)
        self._subentry_id = subentry_id
        self._attr_unique_id = f"{subentry_id}_problem"
        self._attr_device_info = zone_device(controller, subentry_id)

    @property
    def is_on(self) -> bool:
        """Gibt es ein Problem in dieser Zone?"""
        return bool(self.controller.zones[self._subentry_id].problems)

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        """Arten der aktuellen Probleme."""
        return {"problems": sorted(self.controller.zones[self._subentry_id].problems)}
