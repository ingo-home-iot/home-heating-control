"""Tests für den Einrichtungsdialog."""

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.home_heating_control import const

pytestmark = pytest.mark.usefixtures("custom_integrations")

GLOBAL_INPUT = {
    const.CONF_BASE_TEMP: "sensor.basis",
    const.CONF_OUTDOOR_TEMP: "sensor.aussen",
    const.CONF_SCHEDULE: "schedule.zeit",
    const.CONF_PERSONS: ["person.test_user"],
    const.CONF_FROST_THRESHOLD: 5,
    const.CONF_AWAY_ECO: True,
    const.CONF_REACTION_TIME: 3,
}


async def test_user_flow_creates_entry_once(hass: HomeAssistant) -> None:
    """Einrichtung legt einen Eintrag an; ein zweiter wird abgelehnt."""
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], GLOBAL_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_BASE_TEMP] == "sensor.basis"

    again = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    assert again["type"] is FlowResultType.ABORT


async def test_zone_subentry_flow(hass: HomeAssistant) -> None:
    """Zone anlegen; gleicher Name wird abgelehnt."""
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], GLOBAL_INPUT
    )
    entry = result["result"]
    hass.states.async_set("climate.trv", "heat")

    zone_input = {
        "name": "Bad",
        const.CONF_THERMOSTATS: ["climate.trv"],
        const.CONF_COMFORT_OFFSET: -1,
        const.CONF_ECO_OFFSET: -3,
        const.CONF_ECO_RELATIVE: False,
    }
    flow = await hass.config_entries.subentries.async_init(
        (entry.entry_id, const.SUBENTRY_ZONE), context={"source": SOURCE_USER}
    )
    assert flow["type"] is FlowResultType.FORM
    done = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], dict(zone_input)
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert [s.title for s in entry.subentries.values()] == ["Bad"]

    flow = await hass.config_entries.subentries.async_init(
        (entry.entry_id, const.SUBENTRY_ZONE), context={"source": SOURCE_USER}
    )
    dup = await hass.config_entries.subentries.async_configure(
        flow["flow_id"], dict(zone_input)
    )
    assert dup["type"] is FlowResultType.FORM
    assert dup["errors"] == {"name": "name_exists"}


def _setup_registry(hass: HomeAssistant) -> None:
    """Zwei Räume: Büro (1 Thermostat, 1 Fensterkontakt), Bad (2 Thermostate, 2 Kontakte)."""
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import entity_registry as er

    areas = ar.async_get(hass)
    ents = er.async_get(hass)
    office = areas.async_create("Büro")
    bath = areas.async_create("Bad")

    def add(domain, uid, area, device_class=None):
        entry = ents.async_get_or_create(
            domain, "test", uid, original_device_class=device_class
        )
        ents.async_update_entity(entry.entity_id, area_id=area.id)
        return entry.entity_id

    add("climate", "c1", office)
    add("binary_sensor", "w1", office, "window")
    add("climate", "c2", bath)
    add("climate", "c3", bath)
    add("binary_sensor", "w2", bath, "window")
    add("binary_sensor", "w3", bath, "opening")


async def test_user_flow_creates_zones_from_areas(hass: HomeAssistant) -> None:
    """Räume mit Thermostaten werden zu Zonen; Fenster nur bei genau einem Kontakt."""
    _setup_registry(hass)
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], GLOBAL_INPUT
    )
    assert result["step_id"] == "areas"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {const.CONF_AREAS: list(result["data_schema"]({})[const.CONF_AREAS])},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    zones = {s.title: s for s in result["result"].subentries.values()}
    assert set(zones) == {"Büro", "Bad"}
    assert len(zones["Bad"].data[const.CONF_THERMOSTATS]) == 2
    assert const.CONF_WINDOW not in zones["Bad"].data
    assert zones["Büro"].data[const.CONF_WINDOW].startswith("binary_sensor.")
    assert zones["Büro"].data[const.CONF_ECO_OFFSET] == -3


async def test_reconfigure_adds_only_new_areas(hass: HomeAssistant) -> None:
    """Beim Ändern werden nur Räume ohne Zone angeboten."""
    _setup_registry(hass)
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], GLOBAL_INPUT
    )
    default = list(result["data_schema"]({})[const.CONF_AREAS])
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_AREAS: default[:1]}
    )
    entry = result["result"]
    assert len(entry.subentries) == 1

    flow = await hass.config_entries.flow.async_init(
        const.DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert flow["step_id"] == "reconfigure"
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], GLOBAL_INPUT)
    assert flow["step_id"] == "areas"
    offered = list(flow["data_schema"]({})[const.CONF_AREAS])
    assert len(offered) == 1 and offered[0] not in default[:1]
    done = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {const.CONF_AREAS: offered}
    )
    assert done["type"] is FlowResultType.ABORT
    await hass.async_block_till_done()
    assert len(entry.subentries) == 2


async def test_reconfigure_skips_areas_with_manual_zone(hass: HomeAssistant) -> None:
    """Ein von Hand angelegter Raum wird nicht doppelt angeboten."""
    _setup_registry(hass)
    from homeassistant.helpers import entity_registry as er

    office_trv = next(
        e.entity_id
        for e in er.async_get(hass).entities.values()
        if e.domain == "climate" and e.area_id == "buro"
    )
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], GLOBAL_INPUT
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_AREAS: []}
    )
    entry = result["result"]
    flow = await hass.config_entries.subentries.async_init(
        (entry.entry_id, const.SUBENTRY_ZONE), context={"source": SOURCE_USER}
    )
    await hass.config_entries.subentries.async_configure(
        flow["flow_id"],
        {
            "name": "Arbeitszimmer",
            const.CONF_THERMOSTATS: [office_trv],
            const.CONF_COMFORT_OFFSET: -4,
            const.CONF_ECO_OFFSET: -4,
            const.CONF_ECO_RELATIVE: False,
        },
    )
    await hass.async_block_till_done()
    flow = await hass.config_entries.flow.async_init(
        const.DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], GLOBAL_INPUT)
    assert list(flow["data_schema"]({})[const.CONF_AREAS]) == ["bad"]
