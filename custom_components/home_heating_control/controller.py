"""Controller: sammelt Eingangswerte, entscheidet je Zone und steuert die Thermostate.

Die eigentliche Entscheidung steckt in engine.py. Dieser Teil kümmert sich um
Auslöser, Entprellung des Fensters, Befehle nur bei Änderung und die Anzeige-Entitäten.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_call_later,
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from . import const
from .engine import (
    Decision,
    HvacTarget,
    ZoneInputs,
    comfort_temperature,
    decide,
    eco_temperature,
    frost,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class Zone:
    """Laufzeitzustand einer Zone."""

    subentry_id: str
    name: str
    thermostats: list[str]
    window_entity: str | None
    comfort_offset: float
    eco_offset: float
    eco_relative: bool
    eco: bool = False
    enabled: bool = True
    window_open: bool = False
    decision: Decision | None = None
    comfort_temp: int | None = None
    eco_temp: int | None = None
    window_timer: CALLBACK_TYPE | None = field(default=None, repr=False)


def _float_state(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Zahlenwert eines Sensors, None wenn nicht verfügbar oder keine Zahl."""
    if entity_id is None:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


class HeatingController:
    """Steuert alle Zonen einer Integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        data = entry.data
        self._base_entity: str = data[const.CONF_BASE_TEMP]
        self._outdoor_entity: str = data[const.CONF_OUTDOOR_TEMP]
        self._schedule_entity: str = data[const.CONF_SCHEDULE]
        self._persons: list[str] = list(data[const.CONF_PERSONS])
        self._frost_threshold: float = float(
            data.get(const.CONF_FROST_THRESHOLD, const.DEFAULT_FROST_THRESHOLD)
        )
        self.disabled_min_temp: float = float(const.DEFAULT_DISABLED_MIN_TEMP)
        self._away_eco: bool = bool(data.get(const.CONF_AWAY_ECO, True))
        self._reaction_time: float = float(
            data.get(const.CONF_REACTION_TIME, const.DEFAULT_REACTION_TIME)
        )

        self.flags: dict[str, bool] = dict.fromkeys(const.FLAGS, False)
        self.correction: float = 0.0
        self.party_hours: float = float(const.DEFAULT_PARTY_HOURS)
        self.party_temp: float = float(const.DEFAULT_PARTY_TEMP)
        self.party_until: datetime | None = None
        self._party_unsub: CALLBACK_TYPE | None = None
        self.zones: dict[str, Zone] = {}
        for subentry_id, subentry in entry.subentries.items():
            if subentry.subentry_type != const.SUBENTRY_ZONE:
                continue
            sub = subentry.data
            self.zones[subentry_id] = Zone(
                subentry_id=subentry_id,
                name=subentry.title,
                thermostats=list(sub[const.CONF_THERMOSTATS]),
                window_entity=sub.get(const.CONF_WINDOW),
                comfort_offset=float(sub.get(const.CONF_COMFORT_OFFSET, 0)),
                eco_offset=float(sub.get(const.CONF_ECO_OFFSET, 0)),
                eco_relative=bool(sub.get(const.CONF_ECO_RELATIVE, False)),
            )

        self.skip_reload = False
        self._frost_active: bool | None = None
        self._running = False
        self._dirty = False
        self._started = False
        self._unsubs: list[CALLBACK_TYPE] = []

    # --- Lebenszyklus -----------------------------------------------------------------

    async def async_start(self) -> None:
        """Auslöser registrieren, erste Berechnung nach dem Start von HA."""
        watched = {self._base_entity, self._schedule_entity, *self._persons}
        window_map = {
            zone.window_entity: zone
            for zone in self.zones.values()
            if zone.window_entity
        }
        watched.update(window_map)
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, sorted(watched), self._handle_state_change
            )
        )
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, [self._outdoor_entity], self._handle_outdoor_change
            )
        )
        self._unsubs.append(async_at_started(self.hass, self._handle_started))

    @callback
    def async_stop(self) -> None:
        """Alle Auslöser und Zeitgeber beenden."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._cancel_party_timer()
        for zone in self.zones.values():
            if zone.window_timer:
                zone.window_timer()
                zone.window_timer = None

    async def _handle_started(self, _hass: HomeAssistant) -> None:
        self._started = True
        for zone in self.zones.values():
            zone.window_open = self._window_live(zone)
        self._frost_active = self._frost_now()
        self.request_update()

    # --- Auslöser ---------------------------------------------------------------------

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        for zone in self.zones.values():
            if zone.window_entity == entity_id:
                self._debounce_window(zone)
                return
        self.request_update()

    @callback
    def _handle_outdoor_change(self, _event: Event[EventStateChangedData]) -> None:
        """Außentemperatur: nur neu berechnen, wenn sich der Frost-Zustand ändert."""
        now = self._frost_now()
        if now != self._frost_active:
            self._frost_active = now
            self.request_update()

    @callback
    def _debounce_window(self, zone: Zone) -> None:
        if zone.window_timer:
            zone.window_timer()
            zone.window_timer = None
        if self._reaction_time <= 0:
            zone.window_open = self._window_live(zone)
            self.request_update()
            return

        @callback
        def _commit(_now: Any) -> None:
            zone.window_timer = None
            zone.window_open = self._window_live(zone)
            self.request_update()

        zone.window_timer = async_call_later(self.hass, self._reaction_time, _commit)

    # --- Eingaben von den Entitäten ------------------------------------------------------

    @callback
    def set_flag(self, name: str, value: bool, *, update: bool = True) -> None:
        """Globalen Schalter setzen. ECO und Komfort dauerhaft schließen sich aus."""
        self.flags[name] = value
        if value and name == const.FLAG_ECO:
            self.flags[const.FLAG_COMFORT_ALWAYS] = False
        elif value and name == const.FLAG_COMFORT_ALWAYS:
            self.flags[const.FLAG_ECO] = False
        if update:
            self.request_update()

    @callback
    def set_correction(self, value: float, *, update: bool = True) -> None:
        """Globale Korrektur der Basis-Solltemperatur setzen."""
        self.correction = value
        if update:
            self.request_update()

    @callback
    def set_disabled_min_temp(self, value: float, *, update: bool = True) -> None:
        """Mindesttemperatur für ausgeschaltete Zonen bei Frost (0 = aus)."""
        self.disabled_min_temp = value
        if update:
            self.request_update()

    @callback
    def set_party_temp(self, value: float, *, update: bool = True) -> None:
        """Zieltemperatur während der Party (0 = Komforttemperatur der Zone)."""
        self.party_temp = value
        if update:
            self.request_update()

    @callback
    def set_party_hours(self, value: float) -> None:
        """Dauer der nächsten Party in Stunden (0 = unbegrenzt). Wirkt ab dem nächsten Start."""
        self.party_hours = value

    @callback
    def start_party(self) -> None:
        """Party starten. Mit Dauer > 0 endet sie nach dieser Zeit von selbst."""
        until = (
            dt_util.utcnow() + timedelta(hours=self.party_hours)
            if self.party_hours > 0
            else None
        )
        self._set_party(until)

    @callback
    def restore_party(self, until: datetime | None) -> None:
        """Party nach einem Neustart fortsetzen; abgelaufene Party bleibt aus."""
        if until is not None and until <= dt_util.utcnow():
            self._set_party_off()
            return
        self._set_party(until, update=False)

    @callback
    def stop_party(self) -> None:
        """Party beenden (von Hand oder nach Ablauf der Dauer)."""
        self._set_party_off()
        self.request_update()

    @callback
    def _set_party(self, until: datetime | None, *, update: bool = True) -> None:
        self._cancel_party_timer()
        self.flags[const.FLAG_PARTY] = True
        self.party_until = until
        if until is not None:
            self._party_unsub = async_track_point_in_utc_time(
                self.hass, self._party_expired, until
            )
        if update:
            self.request_update()

    @callback
    def _set_party_off(self) -> None:
        self._cancel_party_timer()
        self.flags[const.FLAG_PARTY] = False
        self.party_until = None

    @callback
    def _cancel_party_timer(self) -> None:
        if self._party_unsub is not None:
            self._party_unsub()
            self._party_unsub = None

    @callback
    def _party_expired(self, _now: datetime) -> None:
        """Dauer abgelaufen: Party beenden und Schalter in der Anzeige nachziehen."""
        self._party_unsub = None
        _LOGGER.info("Party-Dauer abgelaufen, Party wird beendet")
        self.stop_party()
        async_dispatcher_send(self.hass, const.signal_update(self.entry.entry_id))

    @callback
    def set_zone_eco_offset(
        self, subentry_id: str, value: float, *, update: bool = True
    ) -> None:
        """Eco-Absenkung einer Zone setzen (Abweichung von der Basis-Solltemperatur)."""
        self.zones[subentry_id].eco_offset = value
        if update:
            self.request_update()

    @callback
    def save_zone_eco_offset(self, subentry_id: str, value: float) -> None:
        """Wert dauerhaft in der Zoneneinstellung ablegen, ohne Neuladen der Integration."""
        subentry = self.entry.subentries[subentry_id]
        self.skip_reload = True
        if not self.hass.config_entries.async_update_subentry(
            self.entry, subentry, data={**subentry.data, const.CONF_ECO_OFFSET: value}
        ):
            self.skip_reload = False

    @callback
    def set_zone_enabled(
        self, subentry_id: str, value: bool, *, update: bool = True
    ) -> None:
        """Heizung einer einzelnen Zone ein- oder ausschalten."""
        self.zones[subentry_id].enabled = value
        if update:
            self.request_update()

    @callback
    def set_zone_eco(
        self, subentry_id: str, value: bool, *, update: bool = True
    ) -> None:
        """ECO einer Zone setzen."""
        self.zones[subentry_id].eco = value
        if update:
            self.request_update()

    # --- Berechnung ------------------------------------------------------------------------

    def _window_live(self, zone: Zone) -> bool:
        if zone.window_entity is None:
            return False
        state = self.hass.states.get(zone.window_entity)
        return state is not None and state.state == STATE_ON

    def _frost_now(self) -> bool:
        return frost(
            _float_state(self.hass, self._outdoor_entity), self._frost_threshold
        )

    def _persons_home(self) -> int:
        count = 0
        for person in self._persons:
            state = self.hass.states.get(person)
            if state is not None and state.state == "home":
                count += 1
        return count

    def _inputs(self, zone: Zone, persons_home: int) -> ZoneInputs:
        base = _float_state(self.hass, self._base_entity)
        schedule = self.hass.states.get(self._schedule_entity)
        return ZoneInputs(
            base_temp=None if base is None else base + self.correction,
            enabled=zone.enabled,
            disabled_min_temp=self.disabled_min_temp,
            comfort_offset=zone.comfort_offset,
            eco_offset=zone.eco_offset,
            eco_relative=zone.eco_relative,
            away_eco_heating=self._away_eco,
            window_open=zone.window_open,
            persons_home=persons_home,
            schedule_on=schedule is not None and schedule.state == STATE_ON,
            winter=self.flags[const.FLAG_WINTER],
            party=self.flags[const.FLAG_PARTY],
            party_temp=self.party_temp,
            comfort_always=self.flags[const.FLAG_COMFORT_ALWAYS],
            eco=self.flags[const.FLAG_ECO] or zone.eco,
            outdoor_temp=_float_state(self.hass, self._outdoor_entity),
            frost_threshold=self._frost_threshold,
        )

    @callback
    def request_update(self) -> None:
        """Neuberechnung anfordern. Mehrere Anforderungen werden zusammengefasst."""
        if not self._started:
            return
        self._dirty = True
        if not self._running:
            self._running = True
            self.entry.async_create_background_task(
                self.hass, self._async_run(), f"{const.DOMAIN} update"
            )

    async def _async_run(self) -> None:
        try:
            while self._dirty:
                self._dirty = False
                self._compute()
                for zone in self.zones.values():
                    await self._async_apply(zone)
        except Exception:
            _LOGGER.exception("Fehler bei der Heizungssteuerung")
        finally:
            self._running = False

    def _compute(self) -> None:
        persons_home = self._persons_home()
        for zone in self.zones.values():
            inputs = self._inputs(zone, persons_home)
            zone.decision = decide(inputs)
            zone.comfort_temp = comfort_temperature(inputs)
            zone.eco_temp = eco_temperature(inputs)
        async_dispatcher_send(self.hass, const.signal_update(self.entry.entry_id))

    # --- Befehle an die Thermostate --------------------------------------------------------

    async def _async_apply(self, zone: Zone) -> None:
        """Sendet Modus und Temperatur nur an Thermostate, deren Wert abweicht."""
        decision = zone.decision
        if decision is None:
            return

        mode_changes = [
            entity_id
            for entity_id in zone.thermostats
            if (state := self.hass.states.get(entity_id)) is not None
            and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
            and state.state != decision.mode.value
        ]
        if mode_changes:
            _LOGGER.info(
                "Zone %s: setze Modus %s (%s) für %s",
                zone.name,
                decision.mode.value,
                decision.reason.value,
                mode_changes,
            )
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": mode_changes, "hvac_mode": decision.mode.value},
                blocking=True,
            )

        if decision.mode is not HvacTarget.HEAT or decision.temperature is None:
            return
        if mode_changes and const.SETTLE_DELAY > 0:
            await asyncio.sleep(const.SETTLE_DELAY)

        target = decision.temperature
        temp_changes = [
            entity_id
            for entity_id in zone.thermostats
            if (state := self.hass.states.get(entity_id)) is not None
            and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
            and _float_attr(state.attributes.get("temperature")) != float(target)
        ]
        if temp_changes:
            _LOGGER.info(
                "Zone %s: setze Temperatur %s (%s) für %s",
                zone.name,
                target,
                decision.reason.value,
                temp_changes,
            )
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": temp_changes, "temperature": target},
                blocking=True,
            )


def _float_attr(value: object) -> float | None:
    """Attributwert als Zahl, None wenn nicht gesetzt oder keine Zahl."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
