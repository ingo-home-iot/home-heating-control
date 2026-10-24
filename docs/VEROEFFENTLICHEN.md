# Home Heating Control auf GitHub veröffentlichen (HACS-Installation und Updates)

Ziel: Jeder kann die Integration über HACS als „Benutzerdefiniertes Repository“ installieren und
Updates mit einem Klick einspielen. Du brauchst dafür nur ein öffentliches GitHub-Repository und
GitHub-Releases. Aufnahme in die HACS-Standardliste ist optional und kommt später.

**Regel für dieses Projekt:** Erst veröffentlichen, wenn du die aktuelle Version am echten System
getestet hast.

---

## Teil 1: Einmalig vorbereiten

### 1. GitHub-Konto und Repository
1. Auf github.com anmelden (oder Konto anlegen, 2-Faktor-Anmeldung einschalten).
2. **New repository**: Name `home-heating-control`, **Public** (HACS funktioniert nur mit öffentlichen
   Repositories), ohne README/Lizenz anlegen (die liegen schon im Projekt).
3. Auf der Repository-Seite oben rechts bei **About** (Zahnrad):
   - **Description**: ein Satz, z. B. „Heizungssteuerung mit Zonen für Home Assistant“. Pflicht, HACS zeigt sie an.
   - **Topics** (Pflicht für HACS): `home-assistant`, `hacs`, `homeassistant`, `heating`, `integration`.

### 2. Platzhalter im Projekt ersetzen
Ersetze `DEIN-GITHUB-NAME` durch deinen GitHub-Benutzernamen.

| Datei | Was ändern |
|---|---|
| `custom_components/home_heating_control/manifest.json` | erledigt: `ingo-home-iot` eingetragen |
| `LICENSE` | Name im Copyright prüfen (derzeit nur „Ingo“; auf Wunsch vollständiger Name) |
| `README.md` | Links, Installationstext (siehe Teil 3), Screenshots/Logo prüfen |
| `docs/TESTANLEITUNG.md` | (ist bereits entfernt, enthielt persönliche Werte) |

Das private Blueprint steht **nicht** im Repository und bleibt privat. Prüfe zur Sicherheit:
`git grep -i -E "blueprint|ingo|anne"` – es sollte nichts Privates mehr zu finden sein
(die Tests dürfen `person.ingo` enthalten, besser ist ein neutraler Name wie `person.test`).

### 3. Git-Autor einstellen
Die bisherigen Commits stammen von „Claude“. Wenn du als Autor erscheinen willst:
```
git config user.name "Dein Name"
git config user.email "deine-github-noreply-adresse"
```
(GitHub-Noreply-Adresse: github.com → Settings → Emails, „Keep my email addresses private“.)
Für künftige Commits gilt dann deine Identität. Die alten Commits können so bleiben; sie zeigen die
Entstehung ehrlich. Willst du sie umschreiben, ist das ein eigener Schritt (frag mich).

### 4. HACS-Dateien prüfen (sind schon vorhanden)
- `hacs.json` im Hauptordner: `{"name": "Home Heating Control", "homeassistant": "2025.3.0"}`.
  Die Mindestversion ist der Test-Stand; wenn du sicher bist, kannst du sie anheben.
- `custom_components/home_heating_control/manifest.json` mit `domain`, `name`, `version`,
  `documentation`, `issue_tracker`, `codeowners` (alle Pflicht für HACS).
- `custom_components/home_heating_control/brand/icon.png` (Logo; HA ab 2026.3 liest es von dort).
- Nur **eine** Integration unter `custom_components/` (ist so).

### 5. Automatische Prüfung (GitHub Actions)
Die Datei `.github/workflows/validate.yml` ist im Projekt. Sie prüft bei jedem Push:
HACS-Regeln (`hacs/action`), Home-Assistant-Regeln (`hassfest`), Lint und Tests.
Nach dem ersten Push im Repository unter **Actions** nachsehen: alle drei Prüfungen sollten grün sein.
Wenn **HACS** rot ist, steht der Grund im Protokoll (meist Beschreibung/Topics/Brand-Bild fehlen).

---

## Teil 2: Erste Veröffentlichung

1. Alles testen (Teil „Definition fertig“ unten) und committen.
2. Repository verbinden und hochladen (im Projektordner):
   ```
   git branch -M main
   git remote add origin https://github.com/DEIN-GITHUB-NAME/home-heating-control.git
   git push -u origin main
   ```
   (GitHub fragt nach der Anmeldung; am einfachsten mit der GitHub-CLI `gh auth login`
   oder einem Personal Access Token.)
3. **Actions** prüfen, bis alles grün ist. Fehler beheben, erneut pushen.
4. **Release erstellen** (ohne Release gibt es keine Versionsauswahl und keine sauberen Updates):
   - Auf GitHub: **Releases → Draft a new release**
   - **Tag**: `v0.1.10` (genau die Version aus `manifest.json`, mit `v` davor), Ziel `main`
   - **Title**: `v0.1.10`
   - **Release notes**: kurz, was neu ist
   - Solange es noch Testphase ist: **Set as a pre-release** anhaken (HACS zeigt Pre-Releases nur
     Nutzern, die „Beta-Versionen anzeigen“ eingeschaltet haben)
   - **Publish release**

   Oder per Kommando:
   ```
   gh release create v0.1.10 --title "v0.1.10" --notes "Erste öffentliche Testversion" --prerelease
   ```
   Wichtig: Ein reiner Tag reicht nicht, es muss ein veröffentlichtes **Release** sein.

---

## Teil 3: So installieren Nutzer es über HACS

(Das gehört in die README.)

1. HACS öffnen → oben rechts **⋮ → Benutzerdefinierte Repositories**.
2. Repository-URL `https://github.com/DEIN-GITHUB-NAME/home-heating-control`, Typ **Integration** → Hinzufügen.
3. Im HACS nach „Home Heating Control“ suchen → **Herunterladen**.
4. **Home Assistant neu starten.**
5. Einstellungen → Geräte & Dienste → **Integration hinzufügen** → „Home Heating Control“.

Fertiger Link zum Einfügen in die README (öffnet HACS direkt):
```
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=DEIN-GITHUB-NAME&repository=home-heating-control&category=integration)
```

---

## Teil 4: Updates veröffentlichen (jedes Mal gleich)

1. Änderung entwickeln, Tests und Lint grün (`pytest`, `ruff check .`, `ruff format .`).
2. **Version hochzählen** in `custom_components/home_heating_control/manifest.json`
   (z. B. `0.1.10` → `0.1.11`). Die Version im Release-Tag muss dazu passen.
3. Committen und pushen:
   ```
   git add -A && git commit -m "fix: kurze Beschreibung" && git push
   ```
4. Actions abwarten (grün).
5. Neues Release mit Tag `v0.1.11` erstellen (wie oben).
6. HACS erkennt die neue Version nach kurzer Zeit selbst (er prüft regelmäßig). Bei den Nutzern erscheint
   unter Einstellungen → Updates ein Eintrag; sofort sehen geht über HACS → die Integration → **⋮ → Neu laden**.
   Nutzer klicken **Aktualisieren** und starten HA neu.

Versionsnummern: `0.1.x` für Fehlerbehebungen und kleine Neuerungen, `0.2.0` bei größeren Neuerungen,
`1.0.0`, wenn du die Integration für stabil hältst. Bei Pre-Releases nach der Zahl `-beta.1` anhängen
(z. B. `v0.2.0-beta.1`), sonst `--prerelease` im Release setzen.

Wichtig für Nutzer-Einstellungen: Ändere nie die Namen bestehender Einstellungs-Schlüssel oder
Entitäts-Kennungen (`unique_id`) – sonst verlieren Nutzer beim Update ihre Zonen und Entitäten.
Neue Optionen bekommen immer einen Standardwert, der das bisherige Verhalten beibehält.

---

## Teil 5: Danach (optional)

- **Issues und Rückmeldungen:** Unter **Issues** melden Nutzer Fehler. Eine Vorlage mit „HA-Version,
  Integrationsversion, Protokollauszug“ spart Rückfragen.
- **Aufnahme in die HACS-Standardliste** (dann ist kein „Benutzerdefiniertes Repository“ mehr nötig):
  erst sinnvoll, wenn die Integration stabil ist und ein paar Nutzer sie nutzen. Voraussetzungen:
  mind. ein veröffentlichtes Release (kein Pre-Release), grüne Actions (HACS und hassfest), Beschreibung,
  Topics, README, Brand-Bild. Antrag per Pull Request im Repository `hacs/default`
  (siehe hacs.xyz → Publish → Include default repositories). Die Prüfung dauert oft Wochen.
- **Offizielle Brand-Bilder:** Die lokalen `brand/`-Bilder genügen für HA ab 2026.3. Ältere HA-Versionen
  zeigen dann kein Logo; das ist unkritisch.

---

## Definition „fertig“ vor jeder Veröffentlichung

- [ ] Am echten Home Assistant getestet (Neustart, Zone, Fenster, Party, ECO)
- [ ] `pytest`, `ruff check .`, `ruff format --check .` grün
- [ ] Version in `manifest.json` erhöht
- [ ] README und `docs/VERHALTEN.md` zu den Änderungen aktuell
- [ ] Keine persönlichen Daten (Entity-IDs, Namen, Blueprint) im Repository
- [ ] Actions auf GitHub grün
- [ ] Release mit passendem Tag veröffentlicht

Quellen: [HACS: Allgemeine Anforderungen](https://hacs.xyz/docs/publish/start),
[HACS: Integrationen](https://hacs.xyz/docs/publish/integration)
