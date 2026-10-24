"""Konstanten von Home Heating Control."""

from __future__ import annotations

DOMAIN = "home_heating_control"

# Globale Einstellungen (Config-Entry)
CONF_BASE_TEMP = "base_temp_entity"
CONF_OUTDOOR_TEMP = "outdoor_temp_entity"
CONF_SCHEDULE = "schedule_entity"
CONF_PERSONS = "person_entities"
CONF_FROST_THRESHOLD = "frost_threshold"
CONF_AWAY_ECO = "away_eco_heating"
CONF_REACTION_TIME = "window_reaction_time"

# Zonen (Subentry)
SUBENTRY_ZONE = "zone"
CONF_THERMOSTATS = "thermostats"
CONF_WINDOW = "window_entity"
CONF_COMFORT_OFFSET = "comfort_offset"
CONF_ECO_OFFSET = "eco_offset"
CONF_ECO_RELATIVE = "eco_relative"
CONF_AREA_ID = "area_id"
CONF_AREAS = "areas"

DEFAULT_ECO_OFFSET = -3

# Globale Schalter
FLAG_WINTER = "winter"
FLAG_PARTY = "party"
FLAG_COMFORT_ALWAYS = "comfort_always"
FLAG_ECO = "eco"
FLAGS = (FLAG_WINTER, FLAG_PARTY, FLAG_COMFORT_ALWAYS, FLAG_ECO)

DEFAULT_FROST_THRESHOLD = 5
DEFAULT_REACTION_TIME = 3
DEFAULT_DISABLED_MIN_TEMP = 5  # °C; 0 = ausgeschaltete Zonen bleiben bei Frost aus
DEFAULT_PARTY_HOURS = 4  # Stunden; 0 = Party endet nicht von selbst
DEFAULT_PARTY_TEMP = 0  # °C; 0 = Party heizt auf die Komforttemperatur der Zone

# Wartezeit zwischen Moduswechsel und Temperaturbefehl (Thermostat kommt zur Ruhe)
SETTLE_DELAY = 3.0


def signal_update(entry_id: str) -> str:
    """Dispatcher-Signal, das alle Entitäten der Integration zum Aktualisieren bringt."""
    return f"{DOMAIN}_{entry_id}_update"
