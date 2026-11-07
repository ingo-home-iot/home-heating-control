<p align="center"><img src="docs/brand/logo.svg" width="128" alt="Home Heating Control"></p>

# Home Heating Control

Heizungssteuerung mit Zonen für Home Assistant. Pro Raum (Zone) entscheidet die Integration anhand von
Zeitplan, Anwesenheit, Fenstern und Frost, ob geheizt wird und auf welche Temperatur (Komfort oder ECO).
Grundlage ist eine **Basis-Solltemperatur**, die du selbst liefern kannst, z. B. aus einer Heizkurve.

> **Status:** frühe Testphase (0.x). Bitte erst an einem Raum ausprobieren und Rückmeldungen als Issue melden.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ingo-home-iot&repository=home-heating-control&category=integration)

## Was sie kann

- **Zonen** aus HA-Bereichen mit Thermostaten, werden bei der Einrichtung automatisch vorgeschlagen
- **Entscheidung** pro Zone: Fenster offen → aus; Heizung aktiv/Party/ECO plus Anwesenheit → Komfort oder ECO;
  Frostschutz bei niedriger Außentemperatur
- **Schalter:** Heizung aktiv, Party (mit Dauer und Zieltemperatur), Komfort dauerhaft, ECO dauerhaft
  (die beiden schließen sich aus), je Zone Heizung und ECO
- **Regler:** Korrektur der Solltemperatur, Mindesttemperatur ausgeschalteter Zonen bei Frost,
  Party-Dauer, Party-Temperatur, je Zone ECO-Absenkung
- Befehle an die Thermostate nur bei echter Abweichung, jeder Befehl steht im Protokoll
- Je Zone ein Sensor „Entscheidung“ mit Grund und Temperaturen

Das genaue Verhalten steht in [docs/VERHALTEN.md](docs/VERHALTEN.md).

## Installation über HACS

1. HACS öffnen → oben rechts **⋮ → Benutzerdefinierte Repositories**
2. URL `https://github.com/ingo-home-iot/home-heating-control`, Typ **Integration**
3. „Home Heating Control" suchen und **Herunterladen**
4. Home Assistant **neu starten**
5. Einstellungen → Geräte & Dienste → **Integration hinzufügen** → Home Heating Control

Solange es nur Pre-Releases gibt, in HACS bei der Integration **Beta-Versionen anzeigen** einschalten.

### Manuell

Den Ordner `custom_components/home_heating_control` nach `/config/custom_components/` kopieren und HA neu starten.

## Einrichtung

Du brauchst: einen Sensor mit der **Basis-Solltemperatur**, einen **Außentemperatur-Sensor**, einen
**Zeitplan** (`schedule`), die **Personen** und Thermostate (`climate`) in Bereichen. Optional je Raum ein
Fenster-/Türkontakt. Die Zonen legt die Einrichtung anhand der Bereiche an, später kannst du sie ändern.

### Bett-Sensor (optional, ab 0.1.12)

In den allgemeinen Einstellungen kannst du einen **Bett-Sensor** (`binary_sensor` oder `input_boolean`, „an" = alle im Bett) wählen und eine **Wartezeit** (Standard 10 Minuten). Je Zone schaltest du **„Folgt dem Bett"** ein (Standard: aus). Ist das Bett belegt, wird der Zeitplan in diesen Zonen unterbrochen und mit ECO-Temperatur geheizt (Grund `bed_eco`). Party und „Komfort dauerhaft" haben Vorrang. Ohne Bett-Sensor ändert sich nichts.

### Vorheizen (optional, ab 0.2.0)

Je Zone schaltest du **„Vorheizen"** ein (Standard: aus). Dann beginnt die Zone schon vor dem nächsten Zeitplanstart, auf Komfort zu heizen, damit der Raum rechtzeitig warm ist. In den allgemeinen Einstellungen legst du fest, wie viele **Minuten ein Grad** Erwärmung etwa dauert (Standard 20) und die **Höchstzeit** (Standard 90 Minuten). Beispiel: Raum 18 °C, Komfort 20 °C, 20 min/Grad → Start 40 Minuten vor dem Zeitplanstart. Der Grund steht dann als `preheat` im Entscheidungssensor. Ohne Schalter ändert sich nichts.

### Handverstellung am Thermostat (optional, ab 0.2.0)

Stellst du ein Thermostat direkt am Ventil um, setzt die Steuerung es sonst beim nächsten Durchlauf zurück. Mit **„Handverstellung respektieren für"** (Minuten, Standard 0 = aus) lässt sie deinen Wert stehen, bis die Zeit um ist oder sich die Lage ändert (z. B. der Zeitplan wechselt). Das Ende steht im Attribut `manual_override_until` des Entscheidungssensors.

### Probleme und Meldungen (ab 0.2.0)

Jede Zone hat einen Diagnose-Sensor **Problem**. Er geht an, wenn ein Thermostat über 30 Minuten nicht erreichbar ist, einen Befehl ablehnt oder (optional) ein Fenster zu lange offen steht. Trägst du in den allgemeinen Einstellungen einen **notify-Dienst** ein (z. B. `notify.mobile_app_mein_handy`), bekommst du dazu eine Meldung. Ohne Eintrag bleibt es beim Sensor, den du auch für eigene Automationen nutzen kannst.

## Entwicklung

```
python3 -m venv venv && venv/bin/pip install pytest-homeassistant-custom-component ruff
venv/bin/python -m pytest -q
venv/bin/ruff check . && venv/bin/ruff format .
```

## Lizenz

MIT, siehe [LICENSE](LICENSE).
