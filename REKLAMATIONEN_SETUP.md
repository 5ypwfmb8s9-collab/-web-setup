# Reklamationen (Ausfallfracht) einrichten

Diese Anleitung verbindet das VW-AI-Programm mit eurem SharePoint/Outlook,
damit Ausfallfracht-PDFs von Duvenbeck automatisch erfasst werden und im
Reiter **Reklamationen** als Dashboard erscheinen.

Prinzip: Alles laeuft ueber **Power Automate** (nicht Copilot Studio) -
Power Automate hat die in eurem Tenant bereits freigegebenen Verbindungen
zu Outlook und SharePoint, daher ist keine separate IT-Freigabe fuer eine
App-Registrierung noetig.

Du brauchst am Ende **3 Flows** + **1 SharePoint-Liste** + **1
Dokumentbibliothek**. Einmal einrichten, laeuft danach automatisch.

## Ueberblick

```
Duvenbeck-Mail (Anhang "...Ausfallfracht...pdf")
        |
        v
Flow 1: "Ausfallfracht erfassen"        (laeuft automatisch im Hintergrund)
        |
        v
SharePoint: Dokumentbibliothek (PDF) + Liste (Metadaten + Status)
        ^                                        |
        |                                        v
Flow 3: "Status aktualisieren"    Flow 2: "Liste abrufen"
        ^                                        |
        |                                        v
        +------------- Python-Programm (Reklamationen-Dashboard) ---+
```

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

## Schritt 1: Flow 1 - "Ausfallfracht erfassen"

In [Power Automate](https://make.powerautomate.com) -> Erstellen ->
Automatisierter Cloudflow.

1. **Trigger**: "Wenn eine neue E-Mail eintrifft (V3)" (Office 365
   Outlook). Postfach: das gemeinsame Team-Postfach auswaehlen (unter
   "Weitere Parameter anzeigen" -> "Postfachadresse", falls es nicht
   dein eigenes Konto ist). "Anhaenge einschliessen" = **Ja**.
   Da ihr die genaue Absenderadresse von Duvenbeck nicht kennt, NICHT
   nach Absender filtern - stattdessen ueber den Anhangnamen filtern
   (naechster Schritt).
2. **Steuerungselement "Anwenden auf jedes"** ueber `Anhaenge` des
   Triggers.
3. Darin eine **Bedingung**: `Name` (aus dem aktuellen Element) ->
   "enthaelt" -> `Ausfallfracht`.
4. Im **Ja-Zweig** der Bedingung:
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
5. Flow speichern, testen (z.B. mit "Flow testen" -> "Manuell" und einer
   Test-Mail mit PDF-Anhang, dessen Name "Ausfallfracht" enthaelt).

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

Um Flow 1 zu testen, ohne auf eine echte Mail zu warten: irgendeine Mail
mit einem PDF-Anhang, dessen Dateiname "Ausfallfracht" enthaelt, an das
Postfach senden (z.B. selbst schicken) und im Power-Automate-Verlauf
("28-Tage-Verlauf") pruefen, ob der Flow ausgeloest wurde und Element +
Datei angelegt wurden.
