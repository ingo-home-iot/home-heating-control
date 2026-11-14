"""Reine Entscheidungslogik der Home Heating Control-Integration.

Keine Abhängigkeit von Home Assistant, damit sie schnell und ohne HA-Instanz getestet
werden kann. Das erwartete Verhalten steht in docs/VERHALTEN.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum


class HvacTarget(StrEnum):
    """Gewünschter Betriebsmodus des Thermostats."""

    HEAT = "heat"
    OFF = "off"


class Reason(StrEnum):
    """Warum die Zone gerade so heizt (für Anzeige und Fehlersuche)."""

    ZONE_DISABLED = "zone_disabled"
    ZONE_FROST_PROTECTION = "zone_frost_protection"
    PARTY = "party"
    WINDOW_OPEN = "window_open"
    HEATING_DISABLED = "heating_disabled"
    FROST_PROTECTION = "frost_protection"
    ECO_FORCED = "eco_forced"
    AWAY_ECO = "away_eco"
    SCHEDULE_COMFORT = "schedule_comfort"
    COMFORT_FORCED = "comfort_forced"
    BED_ECO = "bed_eco"
    PREHEAT = "preheat"
    SCHEDULE_OFF_ECO = "schedule_off_eco"


@dataclass(frozen=True, slots=True)
class ZoneInputs:
    """Alle Eingangswerte einer Zone zum Berechnungszeitpunkt."""

    base_temp: float | None
    enabled: bool = True
    disabled_min_temp: float = 0.0
    comfort_offset: float = 0.0
    eco_offset: float = 0.0
    eco_relative: bool = False
    away_eco_heating: bool = True
    window_open: bool = False
    bed_occupied: bool = False
    preheat: bool = False
    persons_home: int = 0
    schedule_on: bool = False
    winter: bool = False
    party: bool = False
    party_temp: float = 0.0
    comfort_always: bool = False
    eco: bool = False
    outdoor_temp: float | None = None
    frost_threshold: float = 5.0
    sun_reduction: float = 0.0  # °C, die Sonne im Fenster senkt die Komforttemperatur


@dataclass(frozen=True, slots=True)
class Decision:
    """Ergebnis: Modus, Zieltemperatur (nur bei heat und bekannter Basis) und Grund."""

    mode: HvacTarget
    temperature: float | None
    reason: Reason


def round_half_up(value: float) -> int:
    """Auf ganze Zahlen runden, 0,5 immer Richtung plus unendlich (-1,5 wird -1).

    HAs Template-Filter `round(0)` rundet dagegen zur geraden Zahl (22,5 wird 22).
    """
    shifted = Decimal(str(value)) + Decimal("0.5")
    return int(shifted.to_integral_value(rounding=ROUND_FLOOR))


def comfort_temperature(inputs: ZoneInputs) -> int | None:
    """Komforttemperatur der Zone, None wenn die Basis fehlt."""
    if inputs.base_temp is None:
        return None
    return round_half_up(inputs.base_temp + inputs.comfort_offset)


def eco_temperature(inputs: ZoneInputs) -> int | None:
    """Eco-Temperatur der Zone, None wenn die Basis fehlt."""
    if inputs.base_temp is None:
        return None
    offset = inputs.eco_offset + (inputs.comfort_offset if inputs.eco_relative else 0.0)
    return round_half_up(inputs.base_temp + offset)


def frost(outdoor_temp: float | None, threshold: float) -> bool:
    """Frost, wenn Außentemperatur <= Grenze. Unbekannter Wert zählt als Frost."""
    if outdoor_temp is None:
        return True
    return outdoor_temp <= threshold


def is_frost(inputs: ZoneInputs) -> bool:
    """Frost für die Eingangswerte einer Zone."""
    return frost(inputs.outdoor_temp, inputs.frost_threshold)


def decide(inputs: ZoneInputs) -> Decision:
    """Berechnet Modus, Zieltemperatur und Grund für eine Zone."""
    if not inputs.enabled:
        if inputs.disabled_min_temp > 0 and is_frost(inputs) and not inputs.window_open:
            return Decision(
                HvacTarget.HEAT,
                round_half_up(inputs.disabled_min_temp),
                Reason.ZONE_FROST_PROTECTION,
            )
        return Decision(HvacTarget.OFF, None, Reason.ZONE_DISABLED)

    if inputs.window_open:
        return Decision(HvacTarget.OFF, None, Reason.WINDOW_OPEN)

    someone_home = inputs.persons_home > 0
    heating_requested = inputs.winter or inputs.party or inputs.eco
    heat_normal = heating_requested and (someone_home or inputs.away_eco_heating)
    heat_frost = (inputs.winter or inputs.party) and is_frost(inputs)

    if not (heat_normal or heat_frost):
        return Decision(HvacTarget.OFF, None, Reason.HEATING_DISABLED)

    comfort_wanted = (
        not inputs.eco
        and someone_home
        and (
            (inputs.schedule_on and not inputs.bed_occupied)
            or inputs.party
            or inputs.comfort_always
            or inputs.preheat
        )
    )

    if comfort_wanted and inputs.party and inputs.party_temp > 0:
        temperature = round_half_up(inputs.party_temp)
        reason = Reason.PARTY
    elif comfort_wanted:
        temperature = comfort_temperature(inputs)
        if inputs.schedule_on:
            reason = Reason.SCHEDULE_COMFORT
        elif inputs.preheat and not (inputs.party or inputs.comfort_always):
            reason = Reason.PREHEAT
        else:
            reason = Reason.COMFORT_FORCED
        # Sonne senkt nur den Komfortwert; Vorheizen soll den Raum warm bekommen
        if (
            temperature is not None
            and inputs.sun_reduction > 0
            and reason is not Reason.PREHEAT
        ):
            temperature = temperature - inputs.sun_reduction
    else:
        temperature = eco_temperature(inputs)
        if inputs.eco:
            reason = Reason.ECO_FORCED
        elif not heat_normal:
            reason = Reason.FROST_PROTECTION
        elif not someone_home:
            reason = Reason.AWAY_ECO
        elif inputs.schedule_on and inputs.bed_occupied:
            reason = Reason.BED_ECO
        else:
            reason = Reason.SCHEDULE_OFF_ECO

    return Decision(HvacTarget.HEAT, temperature, reason)


def sun_share(
    lux: float | None, elevation: float | None, reference: float
) -> float | None:
    """Helligkeit als Anteil des Klarhimmel-Werts bei der aktuellen Sonnenhöhe.

    Klarer Himmel liefert etwa `reference` × sin(Sonnenhöhe) Lux. 1,0 heißt also "so
    hell wie bei klarem Himmel", 0,3 etwa "bedeckt". Gedacht für die Heizperiode
    (Sonnenhöhen bis etwa 35°); im Hochsommer weicht die Näherung ab.
    """
    if lux is None or elevation is None or elevation <= 0 or reference <= 0:
        return None
    return lux / (reference * math.sin(math.radians(elevation)))


def sun_reduction(
    share: float | None,
    low: float,
    high: float,
    max_reduction: float,
    step: float,
) -> float:
    """Absenkung in °C für den Sonnenanteil (siehe `sun_share`).

    Unter `low` keine, zwischen `low` und `high` die halbe, ab `high` die volle Absenkung
    (Schwellen als Anteil, 0,5 = 50 %). Jede Stufe wird auf ganze Schritte der
    Thermostat-Auflösung abgerundet; bei einer Höchstabsenkung von 0,5 und Schritt 0,5
    bleibt es also bei "aus" oder "voll".
    """
    if share is None or max_reduction <= 0:
        return 0.0
    if share >= high:
        part = 1.0
    elif share >= low:
        part = 0.5
    else:
        return 0.0
    return float(int(max_reduction * part / step + 1e-9)) * step


def sun_in_window(
    azimuth: float | None,
    elevation: float | None,
    directions: list[float],
    min_elevation: float,
    max_angle: float,
) -> bool:
    """Scheint die Sonne auf mindestens eines der Fenster (Richtungen als Azimut in Grad)?"""
    if azimuth is None or elevation is None or elevation < min_elevation:
        return False
    for facing in directions:
        diff = abs((azimuth - facing + 180.0) % 360.0 - 180.0)
        if diff <= max_angle:
            return True
    return False
