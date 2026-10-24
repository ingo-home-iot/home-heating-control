"""Globale Schalter und ECO je Zone. Zustände überleben einen Neustart."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import HeatingConfigEntry
from .const import FLAG_PARTY, FLAGS
from .controller import HeatingController
from .entity import HeatingEntity, global_device, zone_device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Schalter anlegen."""
    controller = entry.runtime_data
    async_add_entities(
        FlagSwitch(controller, flag) for flag in FLAGS if flag != FLAG_PARTY
    )
    async_add_entities([PartySwitch(controller)])
    for subentry_id in controller.zones:
        async_add_entities(
            [
                ZoneEnabledSwitch(controller, subentry_id),
                ZoneEcoSwitch(controller, subentry_id),
            ],
            config_subentry_id=subentry_id,
        )


class _RestoringSwitch(HeatingEntity, SwitchEntity, RestoreEntity):
    """Schalter, der seinen Zustand wiederherstellt und im Controller ablegt."""

    _default_on = False

    def _apply(self, value: bool) -> None:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        """Letzten Zustand wiederherstellen (ohne sofortige Neuberechnung)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self._attr_is_on = self._default_on if last is None else last.state == STATE_ON
        self._apply(self._attr_is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Einschalten."""
        self._attr_is_on = True
        self._apply(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Ausschalten."""
        self._attr_is_on = False
        self._apply(False)
        self.async_write_ha_state()


class FlagSwitch(_RestoringSwitch):
    """Globaler Schalter (Heizung aktiv, Party, Komfort dauerhaft, ECO)."""

    def __init__(self, controller: HeatingController, flag: str) -> None:
        super().__init__(controller)
        self._flag = flag
        self._attr_translation_key = flag
        self._attr_unique_id = f"{controller.entry.entry_id}_{flag}"
        self._attr_device_info = global_device(controller)

    @property
    def is_on(self) -> bool:
        """Zustand kommt vom Controller (er schaltet ECO/Komfort dauerhaft gegeneinander aus)."""
        return self.controller.flags[self._flag]

    def _apply(self, value: bool) -> None:
        self.controller.set_flag(self._flag, value)


class PartySwitch(HeatingEntity, SwitchEntity, RestoreEntity):
    """Party: heizt für die eingestellte Dauer, danach schaltet sie sich selbst aus."""

    _attr_translation_key = FLAG_PARTY

    def __init__(self, controller: HeatingController) -> None:
        super().__init__(controller)
        self._attr_unique_id = f"{controller.entry.entry_id}_{FLAG_PARTY}"
        self._attr_device_info = global_device(controller)

    @property
    def is_on(self) -> bool:
        """Zustand kommt vom Controller (er beendet die Party auch von selbst)."""
        return self.controller.flags[FLAG_PARTY]

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Ende der laufenden Party (leer, wenn aus oder ohne Dauer)."""
        until = self.controller.party_until
        return {"ends_at": None if until is None else until.isoformat()}

    async def async_added_to_hass(self) -> None:
        """Nach einem Neustart eine laufende Party mit ihrem Ende fortsetzen."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None or last.state != STATE_ON:
            return
        raw = last.attributes.get("ends_at")
        self.controller.restore_party(
            dt_util.parse_datetime(raw) if isinstance(raw, str) else None
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Party starten."""
        self.controller.start_party()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Party beenden."""
        self.controller.stop_party()
        self.async_write_ha_state()


class ZoneEcoSwitch(_RestoringSwitch):
    """ECO nur für eine Zone."""

    _attr_translation_key = "zone_eco"

    def __init__(self, controller: HeatingController, subentry_id: str) -> None:
        super().__init__(controller)
        self._subentry_id = subentry_id
        self._attr_unique_id = f"{subentry_id}_eco"
        self._attr_device_info = zone_device(controller, subentry_id)

    def _apply(self, value: bool) -> None:
        self.controller.set_zone_eco(self._subentry_id, value)


class ZoneEnabledSwitch(_RestoringSwitch):
    """Heizung nur dieser Zone ein oder aus. Standard: an (bisheriges Verhalten)."""

    _attr_translation_key = "zone_enabled"
    _default_on = True

    def __init__(self, controller: HeatingController, subentry_id: str) -> None:
        super().__init__(controller)
        self._subentry_id = subentry_id
        self._attr_unique_id = f"{subentry_id}_enabled"
        self._attr_device_info = zone_device(controller, subentry_id)

    def _apply(self, value: bool) -> None:
        self.controller.set_zone_enabled(self._subentry_id, value)
