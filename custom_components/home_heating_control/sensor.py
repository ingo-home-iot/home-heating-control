"""Pro Zone ein Sensor, der die aktuelle Entscheidung samt Grund zeigt."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

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
            [ZoneDecisionSensor(controller, subentry_id)],
            config_subentry_id=subentry_id,
        )


class ZoneDecisionSensor(HeatingEntity, SensorEntity):
    """Zeigt den Grund der aktuellen Entscheidung; Details stehen in den Attributen."""

    _attr_translation_key = "decision"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [reason.value for reason in Reason]  # noqa: RUF012

    def __init__(self, controller: HeatingController, subentry_id: str) -> None:
        super().__init__(controller)
        self._subentry_id = subentry_id
        self._attr_unique_id = f"{subentry_id}_decision"
        self._attr_device_info = zone_device(controller, subentry_id)

    @property
    def native_value(self) -> str | None:
        """Grund der aktuellen Entscheidung."""
        decision = self.controller.zones[self._subentry_id].decision
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
        }
