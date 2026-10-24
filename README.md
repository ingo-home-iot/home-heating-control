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

## Entwicklung

```
python3 -m venv venv && venv/bin/pip install pytest-homeassistant-custom-component ruff
venv/bin/python -m pytest -q
venv/bin/ruff check . && venv/bin/ruff format .
```

## Lizenz

MIT, siehe [LICENSE](LICENSE).
