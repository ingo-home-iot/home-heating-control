"""Reine Entscheidungslogik der Home Heating Control-Integration.

Keine Abhängigkeit von Home Assistant, damit sie schnell und ohne HA-Instanz getestet
werden kann. Das erwartete Verhalten steht in docs/VERHALTEN.md.
"""

from __future__ import annotations

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
    persons_home: int = 0
    schedule_on: bool = False
    winter: bool = False
    party: bool = False
    party_temp: float = 0.0
    comfort_always: bool = False
    eco: bool = False
    outdoor_temp: float | None = None
    frost_threshold: float = 5.0


@dataclass(frozen=True, slots=True)
class Decision:
    """Ergebnis: Modus, Zieltemperatur (nur bei heat und bekannter Basis) und Grund."""

    mode: HvacTarget
    temperature: int | None
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
        and (inputs.schedule_on or inputs.party or inputs.comfort_always)
    )

    if comfort_wanted and inputs.party and inputs.party_temp > 0:
        temperature = round_half_up(inputs.party_temp)
        reason = Reason.PARTY
    elif comfort_wanted:
        temperature = comfort_temperature(inputs)
        reason = (
            Reason.SCHEDULE_COMFORT if inputs.schedule_on else Reason.COMFORT_FORCED
        )
    else:
        temperature = eco_temperature(inputs)
        if inputs.eco:
            reason = Reason.ECO_FORCED
        elif not heat_normal:
            reason = Reason.FROST_PROTECTION
        elif not someone_home:
            reason = Reason.AWAY_ECO
        else:
            reason = Reason.SCHEDULE_OFF_ECO

    return Decision(HvacTarget.HEAT, temperature, reason)
