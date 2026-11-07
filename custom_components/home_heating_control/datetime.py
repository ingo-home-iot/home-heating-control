"""Rückkehr-Zeitpunkt für den Urlaubsmodus."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import HeatingConfigEntry
from .controller import HeatingController
from .entity import HeatingEntity, global_device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Rückkehr-Entität anlegen."""
    async_add_entities([VacationReturn(entry.runtime_data)])


class VacationReturn(HeatingEntity, DateTimeEntity, RestoreEntity):
    """Wann kommt ihr aus dem Urlaub zurück? Leer = Urlaub bis zum Ausschalten."""

    _attr_translation_key = "vacation_return"

    def __init__(self, controller: HeatingController) -> None:
        super().__init__(controller)
        self._attr_unique_id = f"{controller.entry.entry_id}_vacation_return"
        self._attr_device_info = global_device(controller)

    @property
    def native_value(self) -> datetime | None:
        """Gespeicherter Rückkehr-Zeitpunkt."""
        back = self.controller.vacation_return
        return None if back is None else dt_util.as_local(back)

    async def async_added_to_hass(self) -> None:
        """Letzten Wert wiederherstellen."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            parsed = dt_util.parse_datetime(last.state)
            if parsed is not None:
                self.controller.set_vacation_return(parsed, update=False)

    async def async_set_value(self, value: datetime) -> None:
        """Neuen Zeitpunkt übernehmen."""
        self.controller.set_vacation_return(value)
        self.async_write_ha_state()
