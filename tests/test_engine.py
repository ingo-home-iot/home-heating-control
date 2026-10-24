"""Tests der Entscheidungslogik gegen docs/VERHALTEN.md."""

from __future__ import annotations

import pytest

from custom_components.home_heating_control.engine import (
    Decision,
    HvacTarget,
    Reason,
    ZoneInputs,
    comfort_temperature,
    decide,
    eco_temperature,
    round_half_up,
)

# Beispielwerte aus dem laufenden Haushalt: Basis 22 °C
BASE = 22.0


def zone(**kwargs: object) -> ZoneInputs:
    """ZoneInputs mit Wintermodus an, Person zu Hause, Basis 22 °C als Ausgangslage."""
    defaults: dict[str, object] = {
        "base_temp": BASE,
        "winter": True,
        "persons_home": 1,
        "outdoor_temp": 9.0,
    }
    defaults.update(kwargs)
    return ZoneInputs(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (21.5, 22),
        (21.4, 21),
        (20.5, 21),  # HAs round(0) ergäbe hier 20 (gerade Zahl)
        (22.5, 23),  # HAs round(0) ergäbe hier 22
        (-0.5, 0),
        (-1.5, -1),
        (22.0, 22),
    ],
)
def test_round_half_up(value: float, expected: int) -> None:
    assert round_half_up(value) == expected


# --- Fenster -----------------------------------------------------------------


def test_window_open_turns_off_even_with_everything_else_on() -> None:
    result = decide(zone(window_open=True, party=True, eco=True))
    assert result == Decision(HvacTarget.OFF, None, Reason.WINDOW_OPEN)


# --- Heizen an/aus -------------------------------------------------------------


def test_winter_off_nothing_else_is_off() -> None:
    result = decide(zone(winter=False))
    assert result == Decision(HvacTarget.OFF, None, Reason.HEATING_DISABLED)


def test_winter_off_but_zone_eco_heats_with_eco_temperature() -> None:
    result = decide(zone(winter=False, eco=True, eco_offset=-5))
    assert result == Decision(HvacTarget.HEAT, 17, Reason.ECO_FORCED)


def test_winter_off_party_heats_comfort_when_home() -> None:
    result = decide(zone(winter=False, party=True, comfort_offset=-1))
    assert result == Decision(HvacTarget.HEAT, 21, Reason.COMFORT_FORCED)


def test_comfort_always_does_not_switch_heating_on() -> None:
    result = decide(zone(winter=False, comfort_always=True))
    assert result.mode is HvacTarget.OFF


# --- Komfort / Eco ---------------------------------------------------------------


def test_schedule_on_and_home_gives_comfort() -> None:
    result = decide(zone(schedule_on=True, comfort_offset=-1, eco_offset=-4))
    assert result == Decision(HvacTarget.HEAT, 21, Reason.SCHEDULE_COMFORT)


def test_schedule_off_and_home_gives_eco() -> None:
    result = decide(zone(schedule_on=False, comfort_offset=-1, eco_offset=-4))
    assert result == Decision(HvacTarget.HEAT, 18, Reason.SCHEDULE_OFF_ECO)


def test_nobody_home_gives_eco_even_if_schedule_on() -> None:
    # Fall aus dem Alltag: 07:00 Uhr, Zeitplan an, niemand zu Hause, Wohnzimmer 22 - 4 = 18 °C
    result = decide(
        zone(persons_home=0, schedule_on=True, comfort_offset=-1, eco_offset=-4)
    )
    assert result == Decision(HvacTarget.HEAT, 18, Reason.AWAY_ECO)


def test_nobody_home_and_no_away_eco_heating_is_off() -> None:
    result = decide(zone(persons_home=0, away_eco_heating=False, outdoor_temp=9.0))
    assert result == Decision(HvacTarget.OFF, None, Reason.HEATING_DISABLED)


def test_zone_eco_overrides_schedule_and_presence() -> None:
    result = decide(
        zone(eco=True, schedule_on=True, party=True, comfort_offset=-3, eco_offset=-5)
    )
    assert result == Decision(HvacTarget.HEAT, 17, Reason.ECO_FORCED)


def test_comfort_always_ignores_schedule_when_home() -> None:
    result = decide(zone(comfort_always=True, schedule_on=False, comfort_offset=-1))
    assert result == Decision(HvacTarget.HEAT, 21, Reason.COMFORT_FORCED)


def test_comfort_always_with_nobody_home_stays_eco() -> None:
    result = decide(zone(comfort_always=True, persons_home=0, eco_offset=-4))
    assert result == Decision(HvacTarget.HEAT, 18, Reason.AWAY_ECO)


# --- Frostschutz -------------------------------------------------------------------


def test_frost_protection_when_away_eco_heating_disabled() -> None:
    result = decide(
        zone(persons_home=0, away_eco_heating=False, outdoor_temp=3.0, eco_offset=-4)
    )
    assert result == Decision(HvacTarget.HEAT, 18, Reason.FROST_PROTECTION)


def test_frost_does_not_apply_without_winter_or_party() -> None:
    result = decide(zone(winter=False, outdoor_temp=-5.0))
    assert result.mode is HvacTarget.OFF


def test_frost_with_decimal_above_threshold_is_not_frost() -> None:
    # 5,9 °C bei Grenze 5: kein Frost (früher wurde auf 5 abgeschnitten)
    result = decide(
        zone(
            persons_home=0, away_eco_heating=False, outdoor_temp=5.9, frost_threshold=5
        )
    )
    assert result.mode is HvacTarget.OFF


def test_unknown_outdoor_temperature_counts_as_frost() -> None:
    result = decide(
        zone(persons_home=0, away_eco_heating=False, outdoor_temp=None, eco_offset=-4)
    )
    assert result == Decision(HvacTarget.HEAT, 18, Reason.FROST_PROTECTION)


# --- Temperaturberechnung ---------------------------------------------------------


@pytest.mark.parametrize(
    ("comfort_offset", "eco_offset", "eco_relative", "comfort", "eco"),
    [
        (-1, -4, False, 21, 18),  # Wohnzimmer
        (-1, -3, False, 21, 19),  # Bad
        (-3, -5, False, 19, 17),  # Küche, Schlafzimmer
        (-4, -4, False, 18, 18),  # Arbeitszimmer: Eco = Komfort (Bestandsverhalten)
        (-1, -4, True, 21, 17),  # relativ: 22 - 1 - 4
        (-4, -4, True, 18, 14),
    ],
)
def test_temperatures_from_household_offsets(
    comfort_offset: float,
    eco_offset: float,
    eco_relative: bool,
    comfort: int,
    eco: int,
) -> None:
    inputs = zone(
        comfort_offset=comfort_offset, eco_offset=eco_offset, eco_relative=eco_relative
    )
    assert comfort_temperature(inputs) == comfort
    assert eco_temperature(inputs) == eco


def test_base_temperature_unavailable_sends_no_temperature() -> None:
    result = decide(zone(base_temp=None, schedule_on=True))
    assert result == Decision(HvacTarget.HEAT, None, Reason.SCHEDULE_COMFORT)


def test_base_temperature_rounds_half_up() -> None:
    result = decide(zone(base_temp=21.5, schedule_on=True))
    assert result.temperature == 22


def test_zone_disabled_is_off_even_with_frost_and_party() -> None:
    """Ausgeschaltete Zone bleibt aus, egal was sonst gilt."""
    result = decide(
        ZoneInputs(
            base_temp=21.0,
            enabled=False,
            winter=True,
            party=True,
            persons_home=1,
            schedule_on=True,
            outdoor_temp=-5.0,
        )
    )
    assert result.mode is HvacTarget.OFF
    assert result.reason is Reason.ZONE_DISABLED
    assert result.temperature is None


def _disabled(**kwargs: object) -> Decision:
    base = {"base_temp": 21.0, "enabled": False, "winter": True, "outdoor_temp": 2.0}
    return decide(ZoneInputs(**{**base, **kwargs}))  # type: ignore[arg-type]


def test_disabled_zone_without_min_temp_stays_off_in_frost() -> None:
    """Ohne Mindesttemperatur bleibt die Zone auch bei Frost aus (bisheriges Verhalten)."""
    assert _disabled().mode is HvacTarget.OFF


def test_disabled_zone_holds_min_temp_in_frost() -> None:
    """Mit Mindesttemperatur: bei Frost heizen auf diese Temperatur."""
    result = _disabled(disabled_min_temp=8.0)
    assert result.mode is HvacTarget.HEAT
    assert result.temperature == 8
    assert result.reason is Reason.ZONE_FROST_PROTECTION


def test_disabled_zone_stays_off_when_mild() -> None:
    """Ohne Frost bleibt die Zone aus, auch mit Mindesttemperatur."""
    assert _disabled(disabled_min_temp=8.0, outdoor_temp=12.0).mode is HvacTarget.OFF


def test_disabled_zone_window_open_stays_off() -> None:
    """Fenster offen schlägt den Frostschutz."""
    assert _disabled(disabled_min_temp=8.0, window_open=True).mode is HvacTarget.OFF


# --- Party-Temperatur ---------------------------------------------------------


def test_party_temperature_replaces_comfort_in_all_zones() -> None:
    result = decide(zone(winter=False, party=True, party_temp=24, comfort_offset=-1))
    assert result == Decision(HvacTarget.HEAT, 24, Reason.PARTY)


def test_party_temperature_beats_schedule_comfort() -> None:
    result = decide(zone(party=True, party_temp=23, schedule_on=True))
    assert result == Decision(HvacTarget.HEAT, 23, Reason.PARTY)


def test_party_temperature_zero_keeps_zone_comfort() -> None:
    result = decide(zone(winter=False, party=True, party_temp=0, comfort_offset=-1))
    assert result == Decision(HvacTarget.HEAT, 21, Reason.COMFORT_FORCED)


def test_party_temperature_is_ignored_without_party() -> None:
    result = decide(zone(party=False, party_temp=24, schedule_on=True))
    assert result == Decision(HvacTarget.HEAT, 22, Reason.SCHEDULE_COMFORT)


def test_party_temperature_is_ignored_for_eco() -> None:
    result = decide(zone(party=True, party_temp=24, eco=True, eco_offset=-3))
    assert result == Decision(HvacTarget.HEAT, 19, Reason.ECO_FORCED)


def test_party_temperature_does_not_override_open_window_or_disabled_zone() -> None:
    assert (
        decide(zone(party=True, party_temp=24, window_open=True)).mode is HvacTarget.OFF
    )
    assert decide(zone(party=True, party_temp=24, enabled=False)).mode is HvacTarget.OFF
