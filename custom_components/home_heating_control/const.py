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
CONF_BED = "bed_entity"
CONF_BED_DELAY = "bed_delay"
CONF_NOTIFY = "notify_service"
CONF_MANUAL = "manual_override_minutes"
CONF_VACATION_LEAD = "vacation_lead_hours"
CONF_WINDOW_ALERT = "window_open_alert"
CONF_PREHEAT_MIN_PER_K = "preheat_minutes_per_kelvin"
CONF_PREHEAT_MAX = "preheat_max_minutes"
CONF_SUN_ENTITY = "sun_entity"
CONF_SUN_LOW = "sun_threshold_low"
CONF_SUN_HIGH = "sun_threshold_high"
CONF_SUN_MAX = "sun_max_reduction"
CONF_SUN_DELAY = "sun_delay_minutes"

# Zonen (Subentry)
SUBENTRY_ZONE = "zone"
CONF_THERMOSTATS = "thermostats"
CONF_WINDOW = "window_entity"
CONF_COMFORT_OFFSET = "comfort_offset"
CONF_ECO_OFFSET = "eco_offset"
CONF_ECO_RELATIVE = "eco_relative"
CONF_FOLLOW_BED = "follow_bed"
CONF_PREHEAT = "preheat"
CONF_ROOM_SENSOR = "room_temp_entity"
CONF_SUN_DIRECTIONS = "sun_directions"
CONF_AREA_ID = "area_id"
CONF_AREAS = "areas"

# Himmelsrichtung der Fenster -> Azimut in Grad (Norden = 0, Osten = 90)
SUN_DIRECTIONS: dict[str, int] = {
    "N": 0,
    "NE": 45,
    "E": 90,
    "SE": 135,
    "S": 180,
    "SW": 225,
    "W": 270,
    "NW": 315,
}

DEFAULT_ECO_OFFSET = -3

# Globale Schalter
FLAG_WINTER = "winter"
FLAG_PARTY = "party"
FLAG_COMFORT_ALWAYS = "comfort_always"
FLAG_ECO = "eco"
FLAGS = (FLAG_WINTER, FLAG_PARTY, FLAG_COMFORT_ALWAYS, FLAG_ECO)

DEFAULT_FROST_THRESHOLD = 5
DEFAULT_REACTION_TIME = 3
DEFAULT_BED_DELAY = 10  # Minuten, bis ein Wechsel des Bett-Zustands wirkt
DEFAULT_VACATION_LEAD = 6  # Stunden vor der Rückkehr wird wieder normal geheizt
VACATION_GRACE_HOURS = 3  # so lange nach der Rückkehr gilt noch "jemand kommt heim"
DEFAULT_MANUAL = 0  # Minuten; 0 = Änderungen am Thermostat werden nicht respektiert
MANUAL_ECHO_SECONDS = (
    60  # so lange gelten Meldungen des Thermostats nach unserem Befehl als Echo
)
DEFAULT_WINDOW_ALERT = 0  # Minuten; 0 = keine Meldung bei lange offenem Fenster
UNAVAILABLE_ALERT_MINUTES = 30  # so lange darf ein Thermostat nicht erreichbar sein
WATCHDOG_INTERVAL = 1  # Minuten zwischen zwei Prüfungen auf Probleme

PROBLEM_UNAVAILABLE = "thermostat_unavailable"
PROBLEM_COMMAND = "command_failed"
PROBLEM_WINDOW = "window_open_long"

DEFAULT_PREHEAT_MIN_PER_K = 20  # Minuten Vorlauf je Kelvin Temperaturunterschied
DEFAULT_PREHEAT_MAX = 90  # Minuten, so früh startet das Vorheizen höchstens
PREHEAT_CHECK_INTERVAL = 5  # Minuten zwischen zwei Prüfungen
DEFAULT_DISABLED_MIN_TEMP = 5  # °C; 0 = ausgeschaltete Zonen bleiben bei Frost aus
DEFAULT_PARTY_HOURS = 4  # Stunden; 0 = Party endet nicht von selbst
DEFAULT_PARTY_TEMP = 0  # °C; 0 = Party heizt auf die Komforttemperatur der Zone
DEFAULT_SUN_LOW = 15000  # lx; ab hier gilt "Sonne scheint" (halbe Absenkung)
DEFAULT_SUN_HIGH = 25000  # lx; ab hier gilt "Sonne scheint kräftig" (volle Absenkung)
DEFAULT_SUN_MAX = 0.5  # °C; größte Absenkung bei Sonne
DEFAULT_SUN_DELAY = 10  # Minuten, die eine neue Sonnenstufe anhalten muss
SUN_STEP = 0.5  # °C; kleinste Schrittweite der Absenkung (Thermostat-Auflösung)
SUN_MIN_ELEVATION = (
    3.0  # Grad über dem Horizont, darunter scheint keine Sonne ins Fenster
)
SUN_WINDOW_ANGLE = 60.0  # Grad; so weit darf die Sonne seitlich vom Fenster stehen
SUN_CHECK_INTERVAL = 5  # Minuten zwischen zwei Prüfungen des Sonnenstands

# Wartezeit zwischen Moduswechsel und Temperaturbefehl (Thermostat kommt zur Ruhe)
SETTLE_DELAY = 3.0


def signal_update(entry_id: str) -> str:
    """Dispatcher-Signal, das alle Entitäten der Integration zum Aktualisieren bringt."""
    return f"{DOMAIN}_{entry_id}_update"
