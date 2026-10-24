"""Globale Korrektur der Basis-Solltemperatur."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HeatingConfigEntry
from .controller import HeatingController
from .entity import HeatingEntity, global_device, zone_device


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeatingConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Regler anlegen: globale Werte am Hauptgerät, ECO-Absenkung je Zone."""
    controller = entry.runtime_data
    async_add_entities(
        [
            CorrectionNumber(controller),
            DisabledMinTempNumber(controller),
            PartyHoursNumber(controller),
            PartyTempNumber(controller),
        ]
    )
    for subentry_id in controller.zones:
        async_add_entities(
            [ZoneEcoOffsetNumber(controller, subentry_id)],
            config_subentry_id=subentry_id,
        )


class CorrectionNumber(HeatingEntity, RestoreNumber):
    """Wird zur Basis-Solltemperatur addiert (alle Zonen)."""

    _attr_translation_key = "correction"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = -10
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, controller: HeatingController) -> None:
        super().__init__(controller)
        self._attr_unique_id = f"{controller.entry.entry_id}_correction"
        self._attr_device_info = global_device(controller)
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        """Letzten Wert wiederherstellen."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self.controller.set_correction(float(self._attr_native_value), update=False)

    async def async_set_native_value(self, value: float) -> None:
        """Neuen Wert übernehmen."""
        self._attr_native_value = value
        self.controller.set_correction(value)
        self.async_write_ha_state()


class DisabledMinTempNumber(HeatingEntity, RestoreNumber):
    """Mindesttemperatur für ausgeschaltete Zonen bei Frost. 0 = Zonen bleiben ganz aus."""

    _attr_translation_key = "disabled_min_temp"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 0
    _attr_native_max_value = 15
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, controller: HeatingController) -> None:
        super().__init__(controller)
        self._attr_unique_id = f"{controller.entry.entry_id}_disabled_min_temp"
        self._attr_device_info = global_device(controller)
        self._attr_native_value = controller.disabled_min_temp

    async def async_added_to_hass(self) -> None:
        """Letzten Wert wiederherstellen."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self.controller.set_disabled_min_temp(
            float(self._attr_native_value), update=False
        )

    async def async_set_native_value(self, value: float) -> None:
        """Neuen Wert übernehmen."""
        self._attr_native_value = value
        self.controller.set_disabled_min_temp(value)
        self.async_write_ha_state()


class PartyHoursNumber(HeatingEntity, RestoreNumber):
    """Dauer einer Party in Stunden. 0 = die Party endet nicht von selbst."""

    _attr_translation_key = "party_hours"
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_native_min_value = 0
    _attr_native_max_value = 24
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, controller: HeatingController) -> None:
        super().__init__(controller)
        self._attr_unique_id = f"{controller.entry.entry_id}_party_hours"
        self._attr_device_info = global_device(controller)
        self._attr_native_value = controller.party_hours

    async def async_added_to_hass(self) -> None:
        """Letzten Wert wiederherstellen."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self.controller.set_party_hours(float(self._attr_native_value))

    async def async_set_native_value(self, value: float) -> None:
        """Neuen Wert übernehmen (gilt ab dem nächsten Party-Start)."""
        self._attr_native_value = value
        self.controller.set_party_hours(value)
        self.async_write_ha_state()


class PartyTempNumber(HeatingEntity, RestoreNumber):
    """Zieltemperatur während der Party in allen Zonen. 0 = Komforttemperatur der Zone."""

    _attr_translation_key = "party_temp"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 0
    _attr_native_max_value = 28
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, controller: HeatingController) -> None:
        super().__init__(controller)
        self._attr_unique_id = f"{controller.entry.entry_id}_party_temp"
        self._attr_device_info = global_device(controller)
        self._attr_native_value = controller.party_temp

    async def async_added_to_hass(self) -> None:
        """Letzten Wert wiederherstellen."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self.controller.set_party_temp(float(self._attr_native_value), update=False)

    async def async_set_native_value(self, value: float) -> None:
        """Neuen Wert übernehmen."""
        self._attr_native_value = value
        self.controller.set_party_temp(value)
        self.async_write_ha_state()


class ZoneEcoOffsetNumber(HeatingEntity, NumberEntity):
    """ECO-Absenkung einer Zone gegenüber der Basis-Solltemperatur.

    Der Regler liest und schreibt direkt die Zoneneinstellung "Abweichung ECO". Es gibt
    nur diesen einen Wert, Regler und Einstellungsdialog sind immer gleich.
    """

    _attr_translation_key = "zone_eco_offset"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = -15
    _attr_native_max_value = 15
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, controller: HeatingController, subentry_id: str) -> None:
        super().__init__(controller)
        self._subentry_id = subentry_id
        self._attr_unique_id = f"{subentry_id}_eco_offset"
        self._attr_device_info = zone_device(controller, subentry_id)
        self._attr_native_value = controller.zones[subentry_id].eco_offset

    async def async_set_native_value(self, value: float) -> None:
        """Wert in die Zoneneinstellung schreiben (ohne die Integration neu zu laden)."""
        self._attr_native_value = value
        self.controller.set_zone_eco_offset(self._subentry_id, value)
        self.async_write_ha_state()
        self.controller.save_zone_eco_offset(self._subentry_id, value)
