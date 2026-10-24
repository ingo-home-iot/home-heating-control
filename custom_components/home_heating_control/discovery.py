"""Räume (Bereiche) mit Thermostaten finden, damit Zonen automatisch angelegt werden können."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

# Sensor-Klassen, die als Fensterkontakt in Frage kommen
WINDOW_CLASSES = ("window", "opening")


@dataclass
class AreaCandidate:
    """Ein Raum mit mindestens einem Thermostat."""

    area_id: str
    name: str
    thermostats: list[str] = field(default_factory=list)
    window: str | None = None


def discover_areas(hass: HomeAssistant, skip_area_ids: set[str]) -> list[AreaCandidate]:
    """Bereiche mit Thermostaten, sortiert nach Name.

    Der Fenstersensor wird nur vorbelegt, wenn der Raum genau einen Sensor der Klasse
    Fenster/Öffnung hat. Bei mehreren Kandidaten bleibt das Feld leer (konservativ).
    """
    area_reg = ar.async_get(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    candidates: dict[str, AreaCandidate] = {}
    windows: dict[str, list[str]] = {}

    for entry in ent_reg.entities.values():
        if entry.disabled_by is not None or entry.hidden_by is not None:
            continue
        if entry.domain not in ("climate", "binary_sensor"):
            continue
        area_id = entry.area_id
        if area_id is None and entry.device_id is not None:
            device = dev_reg.async_get(entry.device_id)
            area_id = device.area_id if device else None
        if area_id is None or area_id in skip_area_ids:
            continue
        area = area_reg.async_get_area(area_id)
        if area is None:
            continue
        if entry.domain == "climate":
            candidate = candidates.setdefault(
                area_id, AreaCandidate(area_id=area_id, name=area.name)
            )
            candidate.thermostats.append(entry.entity_id)
        elif (entry.device_class or entry.original_device_class) in WINDOW_CLASSES:
            windows.setdefault(area_id, []).append(entry.entity_id)

    for area_id, candidate in candidates.items():
        found = windows.get(area_id, [])
        if len(found) == 1:
            candidate.window = found[0]
        candidate.thermostats.sort()
    return sorted(candidates.values(), key=lambda c: c.name.casefold())
