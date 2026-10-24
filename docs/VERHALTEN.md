# Verhalten der Home-Heating-Control-Integration

Diese Beschreibung ist die Grundlage der Implementierung. Der Code wird nach dieser
Beschreibung geschrieben, nicht aus fremdem YAML oder Jinja übersetzt. Änderungen am
Verhalten zuerst hier, dann im Code und in den Tests.

## Begriffe

- **Zone**: ein Raum mit einem oder mehreren Thermostaten (`climate`-Entitäten).
- **Basis-Solltemperatur**: ein Sensor (z. B. aus einer Heizkurve). Daraus werden alle
  Zieltemperaturen berechnet.
- **Komforttemperatur** = Basis + Komfort-Offset der Zone.
- **Eco-Temperatur** = Basis + Eco-Offset der Zone. Optional (`eco_relative`): zusätzlich
  + Komfort-Offset, die Absenkung bezieht sich dann auf die Komforttemperatur der Zone.
- Beide Werte werden auf ganze °C gerundet, 0,5 immer aufwärts (20,5 wird 21, 22,5 wird 23).

## Globale Schalter

| Schalter | Bedeutung |
|---|---|
| Heizung aktiv (Wintermodus) | Aus: es wird nicht geheizt (Ausnahmen: Eco, Party). |
| Party | Heizt auch ohne Wintermodus, Zeitplan wird ignoriert (Komfort, wenn jemand zu Hause ist). Endet nach der eingestellten **Party-Dauer** von selbst; Zieltemperatur siehe **Party-Temperatur**. |
| Komfort dauerhaft | Zeitplan wird ignoriert, Komfort, wenn jemand zu Hause ist. Schaltet die Heizung nicht selbst ein. |
| ECO dauerhaft (global) | Alle Zonen: Eco-Temperatur, es wird geheizt, Zeitplan und Anwesenheit greifen nicht ein. |

**ECO dauerhaft** und **Komfort dauerhaft** schließen sich aus: Wer einen einschaltet, schaltet den anderen aus.

Je Zone gibt es zusätzlich einen eigenen **ECO**-Schalter mit derselben Wirkung nur für diese Zone.

## Party: Dauer und Temperatur

- **Party-Dauer** (Regler am Hauptgerät, Stunden, Standard 4, Schritt 0,5, **0 = endet nicht
  von selbst**). Beim Einschalten der Party wird das Ende berechnet und als Attribut
  `ends_at` am Party-Schalter angezeigt. Nach Ablauf schaltet sich die Party selbst aus.
  Eine Änderung der Dauer wirkt erst ab dem nächsten Start. Von Hand ausschalten beendet
  die Party sofort. Nach einem Neustart von HA läuft eine Party bis zu ihrem Ende weiter,
  eine abgelaufene bleibt aus.
- **Party-Temperatur** (Regler am Hauptgerät, ganze °C, **0 = Komforttemperatur der Zone**,
  Standard 0). Ist sie größer als 0, heizen alle Zonen während der Party auf diesen Wert
  (Grund `party`). Sie gilt nur dort, wo sonst Komfort gelten würde: nicht bei ECO, nicht bei
  offenem Fenster, nicht in ausgeschalteten Zonen, nicht ohne Person zu Hause.

## ECO-Absenkung als Regler

Je Zone gibt es einen Regler **ECO-Absenkung** (−15 bis +15 °C, Schritt 0,5). Er ist
dasselbe wie das Feld „Abweichung ECO" in den Zoneneinstellungen: Der Regler schreibt den Wert
dorthin, und eine Änderung in den Einstellungen zeigt der Regler nach dem Neuladen an. Es gibt
nur einen Wert, beide sind immer gleich.

## Eingänge je Zone

Basis-Solltemperatur, Komfort-Offset, Eco-Offset, Fensterkontakt (optional),
Personen zu Hause (Anzahl), Zeitplan (an/aus), Außentemperatur, Frostgrenze,
Option „bei Abwesenheit mit Eco heizen" (Standard: ja).

## Entscheidung Modus (heat / off)

Reihenfolge, die erste zutreffende Regel gilt:

1. **Fenster offen** → `off`.
2. **Heizen gewünscht**, wenn (Wintermodus oder Party oder ECO) und
   (mindestens eine Person zu Hause **oder** „bei Abwesenheit mit Eco heizen" ist an) → `heat`.
3. **Frostschutz**: (Wintermodus oder Party) und Außentemperatur ≤ Frostgrenze → `heat`.
   Ist der Außensensor nicht verfügbar, gilt das als Frost (sichere Seite).
4. Sonst → `off`.

## Entscheidung Temperatur (nur bei `heat`)

- **Komfort**, wenn: kein ECO und (Zeitplan an oder Party oder Komfort dauerhaft)
  und mindestens eine Person zu Hause.
- Sonst **Eco**-Temperatur (ECO aktiv, niemand zu Hause oder Zeitplan aus).

## Bewusste Abweichungen von Bestandsverhalten

1. Ist die Basis-Solltemperatur nicht verfügbar, wird **keine** Temperatur gesendet
   (Thermostat behält den letzten Wert). Der Modus wird trotzdem gesetzt.
2. Frostvergleich mit Dezimalwerten (5,9 °C zählt bei Grenze 5 nicht als Frost).
3. Rundung: HAs Template-Filter `round(0)` rundet zur geraden Zahl (22,5 wird 22, 20,5 wird 20).
   Die Integration rundet 0,5 immer aufwärts. Bei ganzzahliger Basis und ganzzahligen
   Offsets (wie im Haushalt heute) gibt es keinen Unterschied.
4. Jede Entscheidung trägt einen **Grund** (z. B. `window_open`, `away_eco`,
   `schedule_comfort`), sichtbar als Attribut, damit nachvollziehbar ist, warum ein Raum
   gerade so heizt.

## Befehle an die Thermostate

- Nur senden, wenn Modus oder Zieltemperatur abweichen.
- Nach einem Moduswechsel zu `heat` kurz warten (3 s), dann Temperatur setzen.
- Auslöser für eine Neuberechnung: Änderung von Zeitplan, Basis-Solltemperatur (2 s
  entprellt), Personen, Fenster, Schaltern, Frost-Schwelle überschritten/unterschritten,
  Start von HA.
- Handeingriffe am Thermostat werden nicht sofort zurückgesetzt, sondern beim nächsten
  Auslöser.

## Noch offen (bewusst nicht Teil von Schritt 1)

- Einrichtungsdialog (Zonen, Offsets, Entitäten), Schalter/Zahlen-Entitäten der Integration,
  Übergang der bisherigen Helfer, Anpassung der LUMEN-Heizungskarte.
