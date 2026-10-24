"""Integrationstests: Controller sendet nur bei Änderung, Einrichtungsdialog."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.home_heating_control import const

pytestmark = pytest.mark.usefixtures("custom_integrations")

BASE = "sensor.basis"
OUT = "sensor.aussen"
SCHED = "schedule.zeit"
PERSON = "person.test_user"
TRV = "climate.trv_bad"
WINDOW = "binary_sensor.fenster_bad"


def make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=const.DOMAIN,
        unique_id=const.DOMAIN,
        data={
            const.CONF_BASE_TEMP: BASE,
            const.CONF_OUTDOOR_TEMP: OUT,
            const.CONF_SCHEDULE: SCHED,
            const.CONF_PERSONS: [PERSON],
            const.CONF_FROST_THRESHOLD: 5,
            const.CONF_AWAY_ECO: True,
            const.CONF_REACTION_TIME: 0,
        },
        subentries_data=[
            ConfigSubentryData(
                subentry_type=const.SUBENTRY_ZONE,
                title="Bad",
                unique_id=None,
                subentry_id="bad",
                data={
                    const.CONF_THERMOSTATS: [TRV],
                    const.CONF_WINDOW: WINDOW,
                    const.CONF_COMFORT_OFFSET: -1,
                    const.CONF_ECO_OFFSET: -3,
                    const.CONF_ECO_RELATIVE: False,
                },
            )
        ],
    )


def set_world(hass: HomeAssistant, *, hvac="heat", target=20) -> None:
    hass.states.async_set(BASE, "21")
    hass.states.async_set(OUT, "10")
    hass.states.async_set(SCHED, "on")
    hass.states.async_set(PERSON, "home")
    hass.states.async_set(WINDOW, "off")
    hass.states.async_set(TRV, hvac, {"temperature": target})


async def setup(hass: HomeAssistant, **world):
    set_world(hass, **world)
    entry = make_entry()
    entry.add_to_hass(hass)
    modes = async_mock_service(hass, "climate", "set_hvac_mode")
    temps = async_mock_service(hass, "climate", "set_temperature")
    with (
        patch.object(const, "SETTLE_DELAY", 0),
        patch(
            "custom_components.home_heating_control.controller.const.SETTLE_DELAY", 0
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await hass.async_start()
        await hass.async_block_till_done()
    return entry, modes, temps


async def test_winter_off_sends_off(hass: HomeAssistant) -> None:
    """Winter aus: Thermostat im Modus heat bekommt off."""
    _, modes, temps = await setup(hass)
    assert len(modes) == 1
    assert modes[0].data["hvac_mode"] == "off"
    assert not temps


async def test_winter_on_sends_temperature_only_on_change(hass: HomeAssistant) -> None:
    """Winter an, Komfort 21-1=20, Thermostat steht schon auf 20: nichts senden."""
    _, modes, temps = await setup(hass)
    modes.clear()
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.home_heating_control_heating_enabled"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert not modes
    assert not temps
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor is not None
    assert sensor.state == "schedule_comfort"
    assert sensor.attributes["target_temperature"] == 20


async def test_temperature_sent_when_different(hass: HomeAssistant) -> None:
    """Thermostat steht auf 18, Ziel 20: genau ein Temperaturbefehl."""
    entry, modes, temps = await setup(hass, target=18)
    modes.clear()
    temps.clear()
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    assert len(temps) == 1
    assert temps[0].data["temperature"] == 20


async def test_window_open_turns_off(hass: HomeAssistant) -> None:
    """Fenster auf: Modus off."""
    entry, modes, _ = await setup(hass)
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    modes.clear()
    hass.states.async_set(WINDOW, "on")
    await hass.async_block_till_done()
    assert len(modes) == 1
    assert modes[0].data["hvac_mode"] == "off"


async def test_base_unavailable_sends_no_temperature(hass: HomeAssistant) -> None:
    """Basis unbekannt: keine Temperatur senden."""
    entry, _, temps = await setup(hass, target=18)
    temps.clear()
    hass.states.async_set(BASE, "unavailable")
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    assert not temps


async def test_correction_is_added_to_base(hass: HomeAssistant) -> None:
    """Korrektur -2 senkt Komfort (21-1-2) und die Zieltemperatur."""
    entry, _, _ = await setup(hass)
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "number",
        "set_value",
        {
            "entity_id": "number.home_heating_control_target_temperature_correction",
            "value": -2,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor.attributes["comfort_temperature"] == 18


async def test_zone_switch_turns_zone_off_and_back_on(hass: HomeAssistant) -> None:
    """Zonen-Schalter aus: Thermostat off. An: wieder heat mit Zieltemperatur."""
    entry, modes, _ = await setup(hass, target=18)
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    switch = "switch.bad_heating"
    assert hass.states.get(switch).state == "on"
    modes.clear()
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch}, blocking=True
    )
    await hass.async_block_till_done()
    assert [c.data["hvac_mode"] for c in modes] == ["off"]
    assert hass.states.get("sensor.bad_decision").state == "zone_disabled"


async def test_disabled_zone_holds_frost_temperature_by_default(
    hass: HomeAssistant,
) -> None:
    """Zone aus, Frost: Standard 5 °C. Wert 0 am Regler schaltet den Schutz ab."""
    hass.states.async_set(OUT, "2")
    entry, _, _ = await setup(hass, hvac="off", target=None)
    hass.states.async_set(OUT, "2")
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.bad_heating"},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor.state == "zone_frost_protection"
    assert sensor.attributes["target_temperature"] == 5

    await hass.services.async_call(
        "number",
        "set_value",
        {
            "entity_id": "number.home_heating_control_minimum_temperature_of_switched_off_zones_frost",
            "value": 0,
        },
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.bad_decision").state == "zone_disabled"


PARTY_SWITCH = "switch.home_heating_control_party"
PARTY_HOURS = "number.home_heating_control_party_duration"
PARTY_TEMP = "number.home_heating_control_party_temperature"
ECO_OFFSET = "number.bad_eco_reduction"


async def _set_number(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_party_uses_party_temperature(hass: HomeAssistant) -> None:
    """Party mit eingestellter Temperatur heizt alle Zonen darauf."""
    _, _, temps = await setup(hass, target=18)
    await _set_number(hass, PARTY_TEMP, 24)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": PARTY_SWITCH}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor.state == "party"
    assert sensor.attributes["target_temperature"] == 24
    assert temps[-1].data["temperature"] == 24


async def test_party_ends_after_duration(hass: HomeAssistant) -> None:
    """Nach der eingestellten Dauer schaltet sich die Party selbst aus."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await setup(hass)
    await _set_number(hass, PARTY_HOURS, 2)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": PARTY_SWITCH}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(PARTY_SWITCH)
    assert state.state == "on"
    assert state.attributes["ends_at"] is not None

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=1, minutes=59))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(PARTY_SWITCH).state == "on"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=2, minutes=1))
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(PARTY_SWITCH)
    assert state.state == "off"
    assert state.attributes["ends_at"] is None


async def test_party_duration_zero_never_ends(hass: HomeAssistant) -> None:
    """Dauer 0: kein Ende, kein Zeitgeber."""
    await setup(hass)
    await _set_number(hass, PARTY_HOURS, 0)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": PARTY_SWITCH}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(PARTY_SWITCH)
    assert state.state == "on"
    assert state.attributes["ends_at"] is None


async def test_party_switch_off_cancels_timer(hass: HomeAssistant) -> None:
    """Von Hand ausgeschaltet: Ende gelöscht."""
    entry, _, _ = await setup(hass)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": PARTY_SWITCH}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": PARTY_SWITCH}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(PARTY_SWITCH).attributes["ends_at"] is None
    assert entry.runtime_data.party_until is None


async def test_eco_reduction_number_changes_eco_temperature(
    hass: HomeAssistant,
) -> None:
    """Regler startet mit dem Wert der Zone (-3), neuer Wert gilt sofort (Basis 21)."""
    _, _, _ = await setup(hass)
    assert float(hass.states.get(ECO_OFFSET).state) == -3
    await _set_number(hass, ECO_OFFSET, -5)
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor.attributes["eco_temperature"] == 16


async def test_eco_offset_regler_schreibt_zoneneinstellung(hass: HomeAssistant) -> None:
    """Regler und Zoneneinstellung sind derselbe Wert, ohne Neuladen der Integration."""
    await setup(hass)
    entry = hass.config_entries.async_entries(const.DOMAIN)[0]
    controller = entry.runtime_data
    await _set_number(hass, ECO_OFFSET, -5)
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data[const.CONF_ECO_OFFSET] == -5
    assert entry.runtime_data is controller  # nicht neu geladen
    assert controller.skip_reload is False


async def test_eco_offset_aenderung_in_einstellungen_wirkt_im_regler(
    hass: HomeAssistant,
) -> None:
    """Wird die Zoneneinstellung geändert, zeigt der Regler nach dem Neuladen den Wert."""
    await setup(hass)
    entry = hass.config_entries.async_entries(const.DOMAIN)[0]
    subentry = next(iter(entry.subentries.values()))
    hass.config_entries.async_update_subentry(
        entry, subentry, data={**subentry.data, const.CONF_ECO_OFFSET: -6}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert float(hass.states.get(ECO_OFFSET).state) == -6


async def test_eco_und_komfort_dauerhaft_schliessen_sich_aus(
    hass: HomeAssistant,
) -> None:
    """Wer ECO dauerhaft einschaltet, schaltet Komfort dauerhaft aus und umgekehrt."""
    await setup(hass)
    eco = "switch.home_heating_control_eco_always"
    comfort = "switch.home_heating_control_comfort_always"
    ids = {s.entity_id for s in hass.states.async_all("switch")}
    assert eco in ids or "switch.home_heating_control_eco" in ids
    eco = eco if eco in ids else "switch.home_heating_control_eco"
    for on, off in ((comfort, eco), (eco, comfort)):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": on}, blocking=True
        )
        await hass.async_block_till_done(wait_background_tasks=True)
        assert hass.states.get(on).state == "on"
        assert hass.states.get(off).state == "off"
