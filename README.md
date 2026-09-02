# VW AI

Werkzeugsammlung mit mehreren Reitern: **Ladelisten** (automatisierte
Verarbeitung von Excel-Ladelisten) und **Reklamationen**
(Ausfallfracht-Dashboard). Weitere Werkzeuge folgen.

## Reiter: Ladelisten

Datei(en) hochladen, die Verarbeitung laeuft automatisch, am Ende steht
die fertige `.xlsx`-Datei zum Download bereit.

## Ablauf

1. Eine oder mehrere Excel-Dateien mit dem Blatt **"Avis Lade Listen"**
   hochladen (Zeile 1 = Ueberschriften, Daten ab Zeile 2, identische
   Spaltenstruktur in allen Dateien).
2. Alle Dateien werden auf die 7 Kernspalten (Abholtag, Empfaenger Name,
   Empfaenger Ort, Abladestelle, Plan VL, PAL, Brutto) abgebildet und zu
   einem gemeinsamen Datensatz zusammengefuehrt (Reihenfolge bleibt
   erhalten, keine Sortierung/Deduplizierung, PAL-Spalte bleibt roh/
   unbearbeitet) und als Blatt "Avis Lade Listen" in die Ausgabe geschrieben.
3. Fuer jeden eindeutigen Wert in Spalte K ("Plan VL") wird ein eigenes
   Blatt "LKW &lt;Wert&gt;" mit den zugehoerigen Positionen, Summenformeln,
   Bestaetigungs- und Unterschriftsbereich sowie Druckeinstellungen erzeugt.
   Ein Zusatz wie "-2" (z.B. "BOHDT978-2") gilt als eigenstaendige Kennung
   und bekommt ein eigenes Blatt. Spalte L ("LKW VL") wird bewusst NICHT
   verwendet, da sie in echten Exporten haeufig leer ist.
4. Automatisierte Validierungen pruefen das Ergebnis (Zuordnung,
   Reihenfolge, Summen, Layout, Druckbereich). Schlaegt eine Pruefung fehl,
   wird keine Datei zum Download angeboten.

## Planungsabgleich (optional)

Zusaetzlich zu den Avis-Dateien kann optional eine Planungsdatei (mit dem
Blatt "Planung für Staplerfahrer") hochgeladen werden. Dann wird die
Ausgabedatei um zwei weitere Blaetter ergaenzt:

- **"Planung für Staplerfahrer"**: 1:1-Kopie des Original-Blatts (Werte,
  Formatierung, Spaltenbreiten, verbundene Zellen) - Spalte J ("LKW") wird
  dabei anhand der Abladestelle (Spalte B "KAPI" = Abladestelle in den
  Avis-Daten) neu befuellt. Abladestellen aus einer festen Ignorier-Liste
  (KXG, BAU90, BAU50, CTCT, UPSOR, ACHG, PT02, da diese nie in Avis-Listen
  vorkommen) werden dabei nicht angefasst.
- **"Abweichungen"**: listet je Abladestelle Unterschiede zwischen den in
  der Planung erwarteten und den tatsaechlichen VWPAL/111444-Mengen aus den
  Avis-Daten (fehlende Palette, falscher Typ, abweichende Menge) sowie
  Abladestellen, die nur in den Avis-Daten aber gar nicht in der Planung
  vorkommen.

## Reiter: Reklamationen (Ausfallfracht)

Ausfallfracht-/Storno-PDFs (Duvenbeck) werden per Drag & Drop hochgeladen:

1. Einmalig einen **Basisordner** angeben (z.B. ein mit SharePoint/OneDrive
   synchronisierter Ordner) und auf "Ordner merken" klicken - wird ab dann
   automatisch vorausgefuellt.
2. PDF reinziehen - die Datei wird inhaltlich ausgewertet (siehe unten),
   automatisch in einen Unterordner `Rechnungen_PDF` kopiert (umbenannt
   auf die Beleg-Nr.) und als Zeile in `VW_Reklamationen.xlsx` (Blatt
   "Tabelle1") erfasst.
3. Alle Felder (Status, Pruefdatum, Ergebnis, Bemerkung, ...) sind direkt
   in der Tabelle editierbar - "Aenderungen speichern" schreibt sie in die
   Excel-Datei zurueck.

**PDF-Inhalt wird ausgelesen** (nicht nur der Dateiname):
- **Beleg-Nr. und Eingangsdatum**: aus dem Kasten "Bei Zahlung bitte
  angeben" auf Seite 1 (positionsbasiert - der Wert steht direkt unter
  dem gleich weit links stehenden Label). Die Beleg-Nr. wird der neue
  Dateiname der gespeicherten PDF.
- **Abholtag**: aus dem Fliesstext ("... vom TT.MM.JJJJ" bzw.
  "Abholtag TT.MM.JJ").
- Wird das Layout nicht erkannt (z.B. eine anders aufgebaute PDF), faellt
  das Programm auf eine Schaetzung aus dem Dateinamen zurueck und zeigt
  eine Warnung, statt falsche Werte stillschweigend einzutragen.
- Absender/Betreff werden weiterhin anhand des Original-Dateinamens
  geraten (z.B. "Storno" im Namen -> Storno-Vorlage).

**Automatische Fallordner-Buendelung**: Wird sowohl Beleg-Nr. als auch
Abholtag erkannt, sucht das Programm im **Archiv-Basisordner** (zweites
Eingabefeld, ebenfalls merkbar; `{jahr}` im Pfad wird automatisch durch
das Jahr des Abholtags ersetzt) im Monatsordner (01-12) passend zum
Abholtag nach den drei Dateien `<JJJJMMTT>..._VW_Planung`,
`..._VW_Ladeliste`, `..._VW_Avisierung` (Trennzeichen im Dateinamen
spielen keine Rolle) und kopiert sie zusammen mit der Rechnung in einen
neuen Ordner `Fall-<Beleg-Nr>` unter dem Reklamationen-Basisordner.
Nicht gefundene Dateien werden gemeldet, nicht stillschweigend
ausgelassen.

Kein Power-Automate/SharePoint-Setup noetig. Die Logik dazu liegt in
`reklamation_lokal.py`.

**Alternative (mehr Automatisierung, mehr Einrichtungsaufwand):**
`reklamation_logic.py` + **[REKLAMATIONEN_SETUP.md](REKLAMATIONEN_SETUP.md)**
beschreiben einen Weg ueber Power-Automate-Flows, die Mails automatisch aus
einem Postfach in eine SharePoint-Liste erfassen (aktuell nicht in der
Oberflaeche verdrahtet, aber fertig getestet und nutzbar als Grundlage,
falls das spaeter gewuenscht ist).

## Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Anschliessend im Browser (Adresse wird im Terminal angezeigt, i.d.R.
`http://localhost:8501`) die Quelldatei(en) hochladen. Die Verarbeitung
startet automatisch, Zusammenfassung und Validierung werden angezeigt und
die fertige Datei kann per Download-Button gespeichert werden.

## Nutzung ohne Oberflaeche (CLI)

Die Verarbeitungslogik liegt getrennt von der Oberflaeche in
`ladeliste_logic.py` und laesst sich auch direkt per Kommandozeile
aufrufen:

```bash
python ladeliste_logic.py quelle1.xlsx quelle2.xlsx -o Ladelisten.xlsx
```

## Tests

```bash
pytest
```

Die Tests decken die PAL-Erkennung (inkl. Sonderfaelle wie unterschiedliche
Abstaende, Gross-/Kleinschreibung, mehrfaches Vorkommen, aehnliche aber
andere Ladungstraeger), das Zusammenfuehren mehrerer Quelldateien, die
lokale Drag-&-Drop-Erfassung (Excel-Roundtrip, PDF-Ablage,
Namenskollisionen) sowie den Abruf/Status-Update der
Power-Automate-Variante (mit simulierten HTTP-Antworten) ab.

## Dateien

- `app.py` – Streamlit-Oberflaeche (Start-Seite + Reiter Ladelisten und
  Reklamationen).
- `ladeliste_logic.py` – reine Verarbeitungslogik fuer Ladelisten
  (Zusammenfuehren, LKW-Blaetter erzeugen, Validierung), UI-unabhaengig
  und per CLI nutzbar.
- `reklamation_lokal.py` – aktive Reklamationen-Logik: PDF-Ablage +
  Excel-Erfassung im gewaehlten Basisordner, UI-unabhaengig.
- `reklamation_logic.py` – Abruf/Status-Update ueber die
  Power-Automate-Flows (Alternative, aktuell nicht in der Oberflaeche
  verdrahtet), UI-unabhaengig.
- `REKLAMATIONEN_SETUP.md` – Einrichtung der Power-Automate-Flows +
  SharePoint fuer die Power-Automate-Alternative.
- `tests/test_ladeliste_logic.py`, `tests/test_reklamation_lokal.py`,
  `tests/test_reklamation_logic.py` – pytest-Tests.
- `requirements.txt` – Python-Abhaengigkeiten.
- `.streamlit/secrets.toml.example` – Vorlage fuer die (nicht
  eingecheckte) `secrets.toml` mit den Flow-URLs (nur fuer die
  Power-Automate-Alternative noetig).
