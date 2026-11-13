# Reklamationen (Ausfallfracht) einrichten

Diese Anleitung verbindet das VW-AI-Programm mit eurem SharePoint/Outlook,
damit Ausfallfracht-Rechnungen und Storno-PDFs von Duvenbeck automatisch
erfasst werden und im Reiter **Reklamationen** als Dashboard erscheinen.

Zwei bekannte Mail-Quellen:

| Fall                    | Absender                              | Betreff/Anhang enthaelt |
|-------------------------|----------------------------------------|--------------------------|
| Ausfallfracht-Rechnung  | `noreply@duvenbeck.de`                 | "Rechnung Ausfallfracht zu Frachtbrief" |
| Storno dazu             | `ausfallfrachten-herne@duvenbeck.de`   | "Storno"                 |

Prinzip: Alles laeuft ueber **Power Automate** (nicht Copilot Studio) -
Power Automate hat die in eurem Tenant bereits freigegebenen Verbindungen
zu Outlook und SharePoint, daher ist keine separate IT-Freigabe fuer eine
App-Registrierung noetig.

Du brauchst am Ende **4 Flows** + **1 SharePoint-Liste** + **1
Dokumentbibliothek**. Einmal einrichten, laeuft danach automatisch.

## Ueberblick

- **Flow 1** ("Ausfallfracht erfassen") und **Flow 1b** ("Storno
  erfassen") laufen automatisch im Hintergrund: sie beobachten das
  Postfach, legen die PDF in der SharePoint-Dokumentbibliothek ab und
  erstellen einen Eintrag in der SharePoint-Liste (mit `Typ` =
  `Ausfallfracht` bzw. `Storno`).
- **Flow 2** ("Liste abrufen") und **Flow 3** ("Status aktualisieren")
  werden vom Python-Programm bei Bedarf per HTTP aufgerufen (Flow 2 beim
  Laden/Aktualisieren des Dashboards, Flow 3 beim Speichern eines
  geaenderten Status).

## Schritt 0: SharePoint vorbereiten

Auf eurer SharePoint-Site (der, auf der ihr auch sonst Dateien ablegt):

1. Neue **Dokumentbibliothek** anlegen, z.B. `Ausfallfracht Dokumente`
   (Website-Inhalte -> Neu -> Dokumentbibliothek).
2. Neue **Liste** anlegen, z.B. `Ausfallfracht Reklamationen`
   (Website-Inhalte -> Neu -> Liste -> Leere Liste), mit folgenden Spalten:

   | Spaltenname   | Typ                    | Anmerkung                     |
   |---------------|------------------------|--------------------------------|
   | Title         | Textzeile (Standard)   | Betreff der Mail               |
   | Absender      | Textzeile              |                                 |
   | Empfangsdatum | Datum und Uhrzeit      |                                 |
   | Dateiname     | Textzeile              |                                 |
   | DateiLink     | Hyperlink              | Link zur PDF in der Bibliothek |
   | Status        | Auswahl                | Werte: `Offen`, `In Bearbeitung`, `Erledigt` - Standard: `Offen` |
   | Typ           | Auswahl                | Werte: `Ausfallfracht`, `Storno` - Standard: `Ausfallfracht` |

## Schritt 1: Flow 1 - "Ausfallfracht erfassen"

In [Power Automate](https://make.powerautomate.com) -> Erstellen ->
Automatisierter Cloudflow.

1. **Trigger**: "Wenn eine neue E-Mail eintrifft (V3)" (Office 365
   Outlook). Postfach: das gemeinsame Team-Postfach auswaehlen (unter
   "Weitere Parameter anzeigen" -> "Postfachadresse", falls es nicht
   dein eigenes Konto ist). "Von" = `noreply@duvenbeck.de`.
   "Betreff-Filter" = `Rechnung Ausfallfracht zu Frachtbrief`.
   "Anhaenge einschliessen" = **Ja**.
2. **Steuerungselement "Anwenden auf jedes"** ueber `Anhaenge` des
   Triggers (falls eine Mail mehrere PDFs enthaelt).
3. Darin:
   - Aktion **"Datei erstellen"** (SharePoint): Site = eure Site,
     Ordnerpfad = `/Ausfallfracht Dokumente`, Dateiname = `Name` (aus
     Anhang), Dateiinhalt = `Inhalt` (aus Anhang).
   - Aktion **"Element erstellen"** (SharePoint): Listenname =
     `Ausfallfracht Reklamationen`.
     - `Title` = `Betreff` (aus dem Mail-Trigger)
     - `Absender` = `Von` (aus dem Mail-Trigger)
     - `Empfangsdatum` = `Empfangszeit` (aus dem Mail-Trigger)
     - `Dateiname` = `Name` (aus Anhang)
     - `DateiLink` = Pfad-Ausgabe der Aktion "Datei erstellen" (Feld
       `Pfad` bzw. die zusammengesetzte SharePoint-URL dazu)
     - `Status` = `Offen`
     - `Typ` = `Ausfallfracht`
4. Flow speichern, testen (z.B. mit "Flow testen" -> "Manuell" und einer
   Test-Mail von `noreply@duvenbeck.de` mit passendem Betreff).

## Schritt 1b: Flow 1b - "Storno erfassen"

Gleicher Aufbau wie Flow 1, als eigener Flow:

1. **Trigger**: "Wenn eine neue E-Mail eintrifft (V3)", gleiches
   Postfach. "Von" = `ausfallfrachten-herne@duvenbeck.de`.
   "Anhaenge einschliessen" = **Ja**. Kein Betreff-Filter noetig, da der
   Absender hier schon eindeutig ist.
2. **Steuerungselement "Anwenden auf jedes"** ueber `Anhaenge`.
3. Darin:
   - Aktion **"Datei erstellen"** (SharePoint): gleicher Ordnerpfad
     `/Ausfallfracht Dokumente`, Dateiname/Dateiinhalt wie bei Flow 1.
   - Aktion **"Element erstellen"** (SharePoint): gleiche Liste
     `Ausfallfracht Reklamationen`, gleiche Felder wie bei Flow 1, aber:
     - `Status` = `Offen`
     - `Typ` = `Storno`
4. Flow speichern, testen (Test-Mail von
   `ausfallfrachten-herne@duvenbeck.de` mit PDF-Anhang).

**Hinweis:** Die beiden Flows verknuepfen eine Storno-Meldung nicht
automatisch mit der urspruenglichen Ausfallfracht-Rechnung (dafuer
muesste der Inhalt der PDF ausgelesen werden, z.B. die
Frachtbrief-Nummer). Im Dashboard erscheint der Storno-Fall als eigene
Zeile mit `Typ = Storno` - ihr seht ihn direkt neben der zugehoerigen
Rechnung (aehnliches Empfangsdatum) und koennt den Status beider Zeilen
manuell auf `Erledigt` setzen.

## Schritt 2: Flow 2 - "Ausfallfracht Liste abrufen"

Neuer Flow -> **"Instant Cloud Flow"** -> Trigger **"Wenn eine
HTTP-Anfrage empfangen wird"** (kein JSON-Schema noetig, leer lassen).

1. Aktion **"Elemente abrufen"** (SharePoint), Listenname =
   `Ausfallfracht Reklamationen`. Optional: "Sortierreihenfolge" nach
   `Empfangsdatum` absteigend, "Anzahl der abzurufenden Schwellenwerte"
   erhoehen falls mehr als 5000 Eintraege erwartet werden (Standardlimit).
2. Aktion **"Antwort"** (Response):
   - Statuscode: `200`
   - Text (Body): `value` (Ausgabe von "Elemente abrufen")
   - Content-Type-Header: `application/json`
3. Speichern. Danach im Trigger "Wenn eine HTTP-Anfrage empfangen wird"
   auf das Feld klicken -> die **HTTP-POST-URL** erscheint dort (erst
   nach dem ersten Speichern sichtbar). Diese URL kopieren -> das ist
   dein `list_url`.

## Schritt 3: Flow 3 - "Ausfallfracht Status aktualisieren"

Wieder **"Instant Cloud Flow"** -> Trigger **"Wenn eine HTTP-Anfrage
empfangen wird"**. Diesmal mit JSON-Schema, "Beispiel-Payload
verwenden" einfuegen:

```json
{
  "id": "1",
  "status": "Erledigt"
}
```

1. Aktion **"Element aktualisieren"** (SharePoint), Listenname =
   `Ausfallfracht Reklamationen`:
   - `Id` = `id` (aus dem Trigger-Body)
   - `Status` = `status` (aus dem Trigger-Body)
2. Aktion **"Antwort"**: Statuscode `200`, Text z.B. `{"ok": true}`.
3. Speichern, die HTTP-POST-URL kopieren -> das ist dein `update_url`.

## Schritt 4: Programm mit den beiden URLs verbinden

Im Programmordner (`LadelistenTool-Git`) die Datei
`.streamlit/secrets.toml.example` als Vorlage nehmen: Datei kopieren
nach `.streamlit/secrets.toml` (gleicher Ordner, neuer Dateiname) und
die beiden URLs aus Schritt 2 und 3 eintragen:

```toml
[reklamationen]
list_url = "https://prod-....logic.azure.com:443/workflows/.../invoke?..."
update_url = "https://prod-....logic.azure.com:443/workflows/.../invoke?..."
```

**Wichtig:** `secrets.toml` (ohne `.example`) NIEMALS in Git einchecken
oder weitergeben - die URLs wirken wie ein Passwort. Sie ist bereits in
`.gitignore` eingetragen. Jeder Kollege, der das Programm nutzen soll,
braucht diese Datei lokal in seinem eigenen `.streamlit`-Ordner (einmal
per Copy-Paste einrichten, genau wie bei den anderen Konfigurationen).

Danach Programm neu starten (`streamlit run app.py` bzw. der gewohnte
Doppelklick-Weg) - im Reiter **Reklamationen** erscheinen jetzt die
erfassten Ausfallfracht-Faelle, mit Status-Auswahl je Zeile und einem
"Status speichern"-Button.

## Testen ohne echte Duvenbeck-Mail

Um Flow 1/1b zu testen, ohne auf eine echte Mail zu warten: eine Mail mit
PDF-Anhang von genau der erwarteten Absenderadresse (`noreply@duvenbeck.de`
mit passendem Betreff fuer Flow 1, `ausfallfrachten-herne@duvenbeck.de`
fuer Flow 1b) an das Postfach senden - z.B. per Weiterleitung oder indem
ihr euch selbst eine Testmail mit angepasstem Absender im
Exchange-Nachrichtenfluss simuliert - und im Power-Automate-Verlauf
("28-Tage-Verlauf") pruefen, ob der jeweilige Flow ausgeloest wurde und
Element + Datei mit korrektem `Typ` angelegt wurden.
