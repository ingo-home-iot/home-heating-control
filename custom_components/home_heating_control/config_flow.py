"""Einrichtungsdialog: globale Einstellungen und Zonen (als Unterelemente)."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentry,
    ConfigSubentryData,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AREA_ID,
    CONF_AREAS,
    CONF_AWAY_ECO,
    CONF_BASE_TEMP,
    CONF_COMFORT_OFFSET,
    CONF_ECO_OFFSET,
    CONF_ECO_RELATIVE,
    CONF_FROST_THRESHOLD,
    CONF_OUTDOOR_TEMP,
    CONF_PERSONS,
    CONF_REACTION_TIME,
    CONF_SCHEDULE,
    CONF_THERMOSTATS,
    CONF_WINDOW,
    DEFAULT_ECO_OFFSET,
    DEFAULT_FROST_THRESHOLD,
    DEFAULT_REACTION_TIME,
    DOMAIN,
    SUBENTRY_ZONE,
)
from .discovery import AreaCandidate, discover_areas


def _offset_selector() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-15,
            max=15,
            step=0.5,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="°C",
        )
    )


def _global_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_BASE_TEMP, default=defaults.get(CONF_BASE_TEMP, vol.UNDEFINED)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["sensor", "input_number", "number"]
                )
            ),
            vol.Required(
                CONF_OUTDOOR_TEMP,
                default=defaults.get(CONF_OUTDOOR_TEMP, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="temperature"
                )
            ),
            vol.Required(
                CONF_SCHEDULE, default=defaults.get(CONF_SCHEDULE, vol.UNDEFINED)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="schedule")
            ),
            vol.Required(
                CONF_PERSONS, default=defaults.get(CONF_PERSONS, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="person", multiple=True)
            ),
            vol.Required(
                CONF_FROST_THRESHOLD,
                default=defaults.get(CONF_FROST_THRESHOLD, DEFAULT_FROST_THRESHOLD),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=-20,
                    max=20,
                    step=0.5,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="°C",
                )
            ),
            vol.Required(
                CONF_AWAY_ECO,
                default=defaults.get(CONF_AWAY_ECO, True),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_REACTION_TIME,
                default=defaults.get(CONF_REACTION_TIME, DEFAULT_REACTION_TIME),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=300,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
        }
    )


class HomeHeatingControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Globale Einstellungen. Es gibt genau eine Instanz."""

    VERSION = 1

    def __init__(self) -> None:
        self._global: dict[str, Any] = {}
        self._candidates: dict[str, AreaCandidate] = {}

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Zonen werden als Unterelemente angelegt."""
        return {SUBENTRY_ZONE: ZoneSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ersteinrichtung."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            self._global = user_input
            self._candidates = {c.area_id: c for c in discover_areas(self.hass, set())}
            if self._candidates:
                return await self.async_step_areas()
            return self.async_create_entry(
                title="Home Heating Control", data=user_input
            )
        return self.async_show_form(step_id="user", data_schema=_global_schema({}))

    async def async_step_areas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Zonen aus Räumen mit Thermostaten anlegen (Einrichtung und Erweiterung)."""
        if user_input is not None:
            selected = [
                self._candidates[area_id]
                for area_id in user_input[CONF_AREAS]
                if area_id in self._candidates
            ]
            if self.source == SOURCE_RECONFIGURE:
                entry = self._get_reconfigure_entry()
                for candidate in selected:
                    self.hass.config_entries.async_add_subentry(
                        entry, _zone_subentry(candidate)
                    )
                return self.async_update_reload_and_abort(
                    entry, data_updates=self._global
                )
            return self.async_create_entry(
                title="Home Heating Control",
                data=self._global,
                subentries=[_zone_subentry_data(c) for c in selected],
            )
        options = [
            selector.SelectOptionDict(
                value=c.area_id, label=f"{c.name} ({len(c.thermostats)})"
            )
            for c in self._candidates.values()
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_AREAS, default=list(self._candidates)): (
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                )
            }
        )
        return self.async_show_form(step_id="areas", data_schema=schema)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Globale Einstellungen ändern."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            known = {sub.data.get(CONF_AREA_ID) for sub in entry.subentries.values()}
            used = {
                thermostat
                for sub in entry.subentries.values()
                for thermostat in sub.data.get(CONF_THERMOSTATS, [])
            }
            self._global = user_input
            # Räume überspringen, die schon eine Zone haben (auch von Hand angelegte)
            self._candidates = {
                c.area_id: c
                for c in discover_areas(self.hass, known - {None})
                if not used.intersection(c.thermostats)
            }
            if self._candidates:
                return await self.async_step_areas()
            return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_global_schema(dict(entry.data)),
        )


def _zone_subentry_data(candidate: AreaCandidate) -> ConfigSubentryData:
    """Zone aus einem Raum: Name und Thermostate vom Raum, Abweichungen mit Vorgaben."""
    data: dict[str, Any] = {
        CONF_AREA_ID: candidate.area_id,
        CONF_THERMOSTATS: candidate.thermostats,
        CONF_COMFORT_OFFSET: 0,
        CONF_ECO_OFFSET: DEFAULT_ECO_OFFSET,
        CONF_ECO_RELATIVE: False,
    }
    if candidate.window:
        data[CONF_WINDOW] = candidate.window
    return ConfigSubentryData(
        data=data,
        subentry_type=SUBENTRY_ZONE,
        title=candidate.name,
        unique_id=candidate.area_id,
    )


def _zone_subentry(candidate: AreaCandidate) -> ConfigSubentry:
    sub = _zone_subentry_data(candidate)
    return ConfigSubentry(
        data=MappingProxyType(sub["data"]),
        subentry_type=sub["subentry_type"],
        title=sub["title"],
        unique_id=sub["unique_id"],
    )


def _zone_schema(defaults: dict[str, Any]) -> vol.Schema:
    window_default = defaults.get(CONF_WINDOW)
    window_key = vol.Optional(
        CONF_WINDOW, description={"suggested_value": window_default}
    )
    return vol.Schema(
        {
            vol.Required(
                CONF_THERMOSTATS, default=defaults.get(CONF_THERMOSTATS, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate", multiple=True)
            ),
            window_key: selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
            ),
            vol.Required(
                CONF_COMFORT_OFFSET, default=defaults.get(CONF_COMFORT_OFFSET, 0)
            ): _offset_selector(),
            vol.Required(
                CONF_ECO_OFFSET, default=defaults.get(CONF_ECO_OFFSET, -3)
            ): _offset_selector(),
            vol.Required(
                CONF_ECO_RELATIVE, default=defaults.get(CONF_ECO_RELATIVE, False)
            ): selector.BooleanSelector(),
        }
    )


class ZoneSubentryFlow(ConfigSubentryFlow):
    """Eine Zone (Raum oder Raumgruppe) anlegen oder ändern."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Neue Zone."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input.pop("name")).strip()
            if not name:
                errors["name"] = "name_required"
            elif name.casefold() in {
                sub.title.casefold() for sub in self._get_entry().subentries.values()
            }:
                errors["name"] = "name_exists"
            else:
                return self.async_create_entry(title=name, data=user_input)
        schema = _zone_schema({}).extend({vol.Required("name"): str})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Zone ändern."""
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, data=user_input
            )
        return self.async_show_form(
            step_id="reconfigure", data_schema=_zone_schema(dict(subentry.data))
        )
