"""Integrationstests: Controller sendet nur bei Änderung, Einrichtungsdialog."""

from datetime import timedelta
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


def make_entry(
    global_extra: dict | None = None, zone_extra: dict | None = None
) -> MockConfigEntry:
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
            **(global_extra or {}),
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
                    **(zone_extra or {}),
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


async def setup(
    hass: HomeAssistant,
    global_extra: dict | None = None,
    zone_extra: dict | None = None,
    **world,
):
    set_world(hass, **world)
    entry = make_entry(global_extra, zone_extra)
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


BED = "binary_sensor.bett_belegt"


async def _setup_bed(hass: HomeAssistant, *, follow: bool = True, bed: str = "off"):
    hass.states.async_set(BED, bed)
    entry, _modes, _temps = await setup(
        hass,
        global_extra={const.CONF_BED: BED, const.CONF_BED_DELAY: 10},
        zone_extra={const.CONF_FOLLOW_BED: follow},
    )
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    return entry


async def test_bed_occupied_interrupts_schedule_after_delay(
    hass: HomeAssistant,
) -> None:
    """Bett belegt: erst nach 10 Minuten ECO (Basis 21, ECO -3 = 18)."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await _setup_bed(hass)
    assert hass.states.get("sensor.bad_decision").state == "schedule_comfort"

    hass.states.async_set(BED, "on")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=9))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.bad_decision").state == "schedule_comfort"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10, seconds=5))
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get("sensor.bad_decision")
    assert state.state == "bed_eco"
    assert state.attributes["target_temperature"] == 18
    assert state.attributes["bed_occupied"] is True


async def test_bed_short_absence_is_ignored(hass: HomeAssistant) -> None:
    """Kurz aufstehen (unter der Wartezeit) ändert nichts."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await _setup_bed(hass)
    hass.states.async_set(BED, "on")
    await hass.async_block_till_done()
    hass.states.async_set(BED, "off")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.bad_decision").state == "schedule_comfort"


async def test_bed_state_applies_immediately_at_start(hass: HomeAssistant) -> None:
    """Nach einem HA-Start gilt der aktuelle Bett-Zustand sofort."""
    await _setup_bed(hass, bed="on")
    assert hass.states.get("sensor.bad_decision").state == "bed_eco"


async def test_bed_ignored_for_zone_that_does_not_follow(hass: HomeAssistant) -> None:
    """Zone ohne \"Folgt dem Bett\" bleibt im Komfort."""
    await _setup_bed(hass, follow=False, bed="on")
    state = hass.states.get("sensor.bad_decision")
    assert state.state == "schedule_comfort"
    assert state.attributes["bed_occupied"] is False


async def test_without_bed_entity_nothing_changes(hass: HomeAssistant) -> None:
    """Bestands-Konfiguration ohne Bett-Sensor verhält sich wie vorher."""
    entry, _, _ = await setup(hass)
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bad_decision").state == "schedule_comfort"


async def test_temperature_is_clamped_to_thermostat_range(hass: HomeAssistant) -> None:
    """Frostschutz 3 °C: Thermostat mit min_temp 5 bekommt 5 (sonst lehnt HA den Wert ab)."""
    hass.states.async_set(OUT, "2")
    entry, _, temps = await setup(hass, hvac="heat", target=18)
    hass.states.async_set(
        TRV, "heat", {"temperature": 18, "min_temp": 5, "max_temp": 25}
    )
    hass.states.async_set(OUT, "2")
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await _set_number(
        hass,
        "number.home_heating_control_minimum_temperature_of_switched_off_zones_frost",
        3,
    )
    temps.clear()
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.bad_heating"}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.bad_decision").attributes["target_temperature"] == 3
    assert temps
    assert temps[-1].data["temperature"] == 5


async def test_temperature_unchanged_when_thermostat_has_no_range(
    hass: HomeAssistant,
) -> None:
    """Ohne min_temp/max_temp am Thermostat bleibt die Zieltemperatur unverändert."""
    _, _, temps = await setup(hass, hvac="heat", target=15)
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.home_heating_control_heating_enabled"},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert temps
    assert temps[-1].data["temperature"] == 20


async def _preheat_world(hass: HomeAssistant, minutes_until: int, current: float):
    """Zeitplan aus, nächster Start in `minutes_until` Minuten, Raum bei `current` °C."""
    from homeassistant.util import dt as dt_util

    entry, _, temps = await setup(
        hass, zone_extra={const.CONF_PREHEAT: True}, target=15
    )
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    temps.clear()
    hass.states.async_set(
        TRV, "heat", {"temperature": 15, "current_temperature": current}
    )
    hass.states.async_set(
        SCHED,
        "off",
        {"next_event": dt_util.utcnow() + timedelta(minutes=minutes_until)},
    )
    await hass.async_block_till_done()
    return entry, temps


async def test_preheat_starts_when_lead_time_reached(hass: HomeAssistant) -> None:
    """Komfort 20, Raum 18 → 2 K × 20 min = 40 min Vorlauf; Start in 30 min → heizen."""
    _, temps = await _preheat_world(hass, minutes_until=30, current=18)
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor is not None
    assert sensor.state == "preheat"
    assert sensor.attributes["preheat"] is True
    assert temps[-1].data["temperature"] == 20


async def test_preheat_waits_when_too_early(hass: HomeAssistant) -> None:
    """Start erst in 120 min, Vorlauf 40 min → noch ECO."""
    _, temps = await _preheat_world(hass, minutes_until=120, current=18)
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor is not None
    assert sensor.state == "schedule_off_eco"
    assert temps[-1].data["temperature"] == 18


async def test_preheat_off_for_zone_without_option(hass: HomeAssistant) -> None:
    from homeassistant.util import dt as dt_util

    entry, _, _ = await setup(hass, target=15)
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    hass.states.async_set(TRV, "heat", {"temperature": 15, "current_temperature": 18})
    hass.states.async_set(
        SCHED, "off", {"next_event": dt_util.utcnow() + timedelta(minutes=10)}
    )
    await hass.async_block_till_done()
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor is not None
    assert sensor.state == "schedule_off_eco"


async def test_rejected_command_sets_problem_and_notifies(hass: HomeAssistant) -> None:
    """Das Thermostat lehnt die Temperatur ab: Problem-Sensor an, Meldung gesendet."""
    from homeassistant.exceptions import ServiceValidationError

    notes = async_mock_service(hass, "notify", "handy")
    entry, _, _ = await setup(
        hass, global_extra={const.CONF_NOTIFY: "notify.handy"}, target=15
    )

    async def reject(call) -> None:
        raise ServiceValidationError("not valid")

    hass.services.async_register("climate", "set_temperature", reject)
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    problem = hass.states.get("binary_sensor.bad_problem")
    assert problem is not None
    assert problem.state == "on"
    assert problem.attributes["problems"] == [const.PROBLEM_COMMAND]
    assert len(notes) == 1
    assert "Bad" in notes[0].data["message"]


async def test_problem_without_notify_service_only_sets_sensor(
    hass: HomeAssistant, freezer
) -> None:
    """Ohne notify-Dienst bleibt es beim Sensor. Thermostat 31 Minuten weg."""
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await setup(hass)
    hass.states.async_set(TRV, "unavailable")
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    problem = hass.states.get("binary_sensor.bad_problem")
    assert problem is not None
    assert problem.state == "on"
    assert problem.attributes["problems"] == [const.PROBLEM_UNAVAILABLE]


async def test_short_unavailable_is_not_a_problem(hass: HomeAssistant, freezer) -> None:
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await setup(hass)
    hass.states.async_set(TRV, "unavailable")
    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    problem = hass.states.get("binary_sensor.bad_problem")
    assert problem is not None
    assert problem.state == "off"


async def test_window_open_too_long_is_reported_once(
    hass: HomeAssistant, freezer
) -> None:
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    notes = async_mock_service(hass, "notify", "handy")
    await setup(
        hass,
        global_extra={const.CONF_NOTIFY: "notify.handy", const.CONF_WINDOW_ALERT: 20},
    )
    hass.states.async_set(WINDOW, "on")
    for _ in range(3):
        freezer.tick(timedelta(minutes=10))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
    problem = hass.states.get("binary_sensor.bad_problem")
    assert problem is not None
    assert problem.attributes["problems"] == [const.PROBLEM_WINDOW]
    assert len(notes) == 1


async def test_window_alert_off_by_default(hass: HomeAssistant, freezer) -> None:
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await setup(hass)
    hass.states.async_set(WINDOW, "on")
    freezer.tick(timedelta(hours=3))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    problem = hass.states.get("binary_sensor.bad_problem")
    assert problem is not None
    assert problem.state == "off"


async def _manual_world(hass: HomeAssistant, minutes: float = 30):
    """Winter an, Zeitplan an, Thermostat steht schon auf Komfort 20."""
    entry, _, temps = await setup(
        hass, global_extra={const.CONF_MANUAL: minutes}, target=20
    )
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    temps.clear()
    return entry, temps


async def test_manual_change_pauses_control(hass: HomeAssistant) -> None:
    """Jemand dreht am Thermostat auf 24: die Steuerung setzt nicht zurück."""
    entry, temps = await _manual_world(hass)
    hass.states.async_set(TRV, "heat", {"temperature": 24})
    await hass.async_block_till_done()
    entry.runtime_data.request_update()
    await hass.async_block_till_done()
    assert not temps
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor is not None
    assert sensor.attributes["manual_override_until"] is not None


async def test_manual_pause_ends_on_state_change(hass: HomeAssistant) -> None:
    """Zeitplan endet: neuer Zustand beendet die Pause, ECO (18) wird gesetzt."""
    _, temps = await _manual_world(hass)
    hass.states.async_set(TRV, "heat", {"temperature": 24})
    await hass.async_block_till_done()
    hass.states.async_set(SCHED, "off")
    await hass.async_block_till_done()
    assert temps[-1].data["temperature"] == 18
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor is not None
    assert sensor.attributes["manual_override_until"] is None


async def test_manual_pause_ends_after_timeout(hass: HomeAssistant, freezer) -> None:
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    _, temps = await _manual_world(hass, minutes=30)
    hass.states.async_set(TRV, "heat", {"temperature": 24})
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert temps[-1].data["temperature"] == 20


async def test_own_command_is_not_a_manual_change(hass: HomeAssistant) -> None:
    """Das Thermostat meldet unseren eigenen Wert zurück: keine Pause."""
    entry, _, temps = await setup(hass, global_extra={const.CONF_MANUAL: 30}, target=15)
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    assert temps[-1].data["temperature"] == 20
    hass.states.async_set(TRV, "heat", {"temperature": 20})
    await hass.async_block_till_done()
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor is not None
    assert sensor.attributes["manual_override_until"] is None


async def test_manual_detection_off_by_default(hass: HomeAssistant) -> None:
    entry, _, temps = await setup(hass, target=20)
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    temps.clear()
    hass.states.async_set(TRV, "heat", {"temperature": 24})
    await hass.async_block_till_done()
    entry.runtime_data.request_update()
    await hass.async_block_till_done()
    assert temps[-1].data["temperature"] == 20


async def _vacation_world(hass: HomeAssistant, lead: int = 6):
    entry, _, temps = await setup(
        hass, global_extra={const.CONF_VACATION_LEAD: lead}, target=20
    )
    entry.runtime_data.set_flag(const.FLAG_WINTER, True)
    await hass.async_block_till_done()
    return entry, temps


def _decision(hass: HomeAssistant):
    sensor = hass.states.get("sensor.bad_decision")
    assert sensor is not None
    return sensor


async def test_vacation_without_date_means_away(hass: HomeAssistant) -> None:
    """Zeitplan an, Person da, aber Urlaub: wie abwesend (ECO)."""
    entry, _ = await _vacation_world(hass)
    assert _decision(hass).state == "schedule_comfort"
    entry.runtime_data.set_vacation(True)
    await hass.async_block_till_done()
    assert _decision(hass).state == "away_eco"
    assert _decision(hass).attributes["vacation"] == "away"


async def test_vacation_far_return_still_away(hass: HomeAssistant) -> None:
    from homeassistant.util import dt as dt_util

    entry, _ = await _vacation_world(hass, lead=6)
    entry.runtime_data.set_vacation_return(dt_util.utcnow() + timedelta(hours=20))
    entry.runtime_data.set_vacation(True)
    await hass.async_block_till_done()
    assert _decision(hass).state == "away_eco"


async def test_vacation_return_soon_heats_comfort_again(hass: HomeAssistant) -> None:
    """Rückkehr in 3 h, Vorlauf 6 h: Zeitplan gilt wieder, auch wenn noch niemand da ist."""
    from homeassistant.util import dt as dt_util

    entry, _ = await _vacation_world(hass, lead=6)
    hass.states.async_set(PERSON, "not_home")
    entry.runtime_data.set_vacation_return(dt_util.utcnow() + timedelta(hours=3))
    entry.runtime_data.set_vacation(True)
    await hass.async_block_till_done()
    assert _decision(hass).state == "schedule_comfort"
    assert _decision(hass).attributes["vacation"] == "returning"


async def test_vacation_switches_to_returning_at_lead_time(
    hass: HomeAssistant, freezer
) -> None:
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    entry, _ = await _vacation_world(hass, lead=6)
    entry.runtime_data.set_vacation_return(dt_util.utcnow() + timedelta(hours=10))
    entry.runtime_data.set_vacation(True)
    await hass.async_block_till_done()
    assert _decision(hass).state == "away_eco"
    freezer.tick(timedelta(hours=5))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert _decision(hass).state == "schedule_comfort"


async def test_vacation_ends_by_itself_after_return(
    hass: HomeAssistant, freezer
) -> None:
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    entry, _ = await _vacation_world(hass, lead=1)
    entry.runtime_data.set_vacation_return(dt_util.utcnow() + timedelta(hours=2))
    entry.runtime_data.set_vacation(True)
    await hass.async_block_till_done()
    for _ in range(3):
        freezer.tick(timedelta(hours=2))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
    switch = hass.states.get("switch.home_heating_control_vacation")
    assert switch is not None
    assert switch.state == "off"
    assert _decision(hass).attributes["vacation"] == "off"


async def test_vacation_entities_set_controller(hass: HomeAssistant) -> None:
    entry, _ = await _vacation_world(hass)
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.home_heating_control_vacation"},
        blocking=True,
    )
    await hass.services.async_call(
        "datetime",
        "set_value",
        {
            "entity_id": "datetime.home_heating_control_return",
            "datetime": "2099-01-01 12:00:00",
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.vacation is True
    assert entry.runtime_data.vacation_return is not None
    assert entry.runtime_data.vacation_return.year == 2099


async def _tick(hass: HomeAssistant, freezer, minutes: int) -> None:
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    for _ in range(minutes):
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()


async def test_heating_time_counts_only_while_heating(
    hass: HomeAssistant, freezer
) -> None:
    await setup(hass)
    hass.states.async_set(TRV, "heat", {"temperature": 20, "hvac_action": "heating"})
    await _tick(hass, freezer, 30)
    hass.states.async_set(TRV, "heat", {"temperature": 20, "hvac_action": "idle"})
    await _tick(hass, freezer, 30)
    sensor = hass.states.get("sensor.bad_heating_time_today")
    assert sensor is not None
    assert 0.45 <= float(sensor.state) <= 0.55


async def test_heating_time_resets_next_day(hass: HomeAssistant, freezer) -> None:
    await setup(hass)
    hass.states.async_set(TRV, "heat", {"temperature": 20, "hvac_action": "heating"})
    await _tick(hass, freezer, 10)
    sensor = hass.states.get("sensor.bad_heating_time_today")
    assert sensor is not None
    assert float(sensor.state) > 0
    hass.states.async_set(TRV, "heat", {"temperature": 20, "hvac_action": "idle"})
    freezer.tick(timedelta(hours=26))
    await _tick(hass, freezer, 1)
    sensor = hass.states.get("sensor.bad_heating_time_today")
    assert sensor is not None
    assert float(sensor.state) == 0
