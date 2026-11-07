"""Pro Zone ein Sensor, der die aktuelle Entscheidung samt Grund zeigt."""

from __future__ import annotations

from datetime import date, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import HeatingConfigEntry
from .controller import HeatingController
from .engine import Reason
from .entity import HeatingEntity, zone_device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sensoren je Zone anlegen."""
    controller = entry.runtime_data
    for subentry_id in controller.zones:
        async_add_entities(
            [
                ZoneDecisionSensor(controller, subentry_id),
                ZoneHeatingTimeSensor(controller, subentry_id),
            ],
            config_subentry_id=subentry_id,
        )


# Während einer Handverstellung zeigt der Sensor das statt des Entscheidungsgrunds
MANUAL_STATE = "manual_override"


class ZoneDecisionSensor(HeatingEntity, SensorEntity):
    """Zeigt den Grund der aktuellen Entscheidung; Details stehen in den Attributen."""

    _attr_translation_key = "decision"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [*(reason.value for reason in Reason), MANUAL_STATE]  # noqa: RUF012

    def __init__(self, controller: HeatingController, subentry_id: str) -> None:
        super().__init__(controller)
        self._subentry_id = subentry_id
        self._attr_unique_id = f"{subentry_id}_decision"
        self._attr_device_info = zone_device(controller, subentry_id)

    @property
    def native_value(self) -> str | None:
        """Grund der aktuellen Entscheidung."""
        zone = self.controller.zones[self._subentry_id]
        if zone.manual_until is not None:
            return MANUAL_STATE
        decision = zone.decision
        return None if decision is None else decision.reason.value

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Modus, Zieltemperatur und die beiden Zwischenwerte."""
        zone = self.controller.zones[self._subentry_id]
        decision = zone.decision
        return {
            "hvac_mode": None if decision is None else decision.mode.value,
            "target_temperature": None if decision is None else decision.temperature,
            "comfort_temperature": zone.comfort_temp,
            "eco_temperature": zone.eco_temp,
            "window_open": zone.window_open,
            "bed_occupied": self.controller.bed_occupied and zone.follow_bed,
            "decision_reason": None if decision is None else decision.reason.value,
            "preheat": zone.preheat_event is not None,
            "vacation": self.controller.vacation_phase(),
            "manual_override_until": None
            if zone.manual_until is None
            else zone.manual_until.isoformat(),
        }


class ZoneHeatingTimeSensor(HeatingEntity, SensorEntity, RestoreEntity):
    """Wie lange die Thermostate der Zone heute aktiv geheizt haben (Stunden)."""

    _attr_translation_key = "heating_time"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 1

    def __init__(self, controller: HeatingController, subentry_id: str) -> None:
        super().__init__(controller)
        self._subentry_id = subentry_id
        self._attr_unique_id = f"{subentry_id}_heating_time"
        self._attr_device_info = zone_device(controller, subentry_id)

    async def async_added_to_hass(self) -> None:
        """Wert von heute nach einem Neustart wiederherstellen."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None:
            return
        try:
            hours = float(last.state)
        except ValueError:
            return
        raw = last.attributes.get("day")
        day = date.fromisoformat(raw) if isinstance(raw, str) else None
        if day is not None:
            self.controller.restore_heating(self._subentry_id, hours, day)

    @property
    def native_value(self) -> float:
        """Heizstunden heute."""
        zone = self.controller.zones[self._subentry_id]
        return round(zone.heating_seconds / 3600, 2)

    @property
    def last_reset(self) -> datetime:
        """Zähler beginnt jeden Tag um Mitternacht neu."""
        return dt_util.start_of_local_day()

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Tag, zu dem der Wert gehört (für die Wiederherstellung)."""
        zone = self.controller.zones[self._subentry_id]
        day = zone.heating_day or dt_util.as_local(dt_util.utcnow()).date()
        return {"day": day.isoformat()}
