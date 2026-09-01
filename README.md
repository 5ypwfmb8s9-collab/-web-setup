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

Zeigt Ausfallfracht-PDFs von Duvenbeck als Dashboard: Absender, Betreff,
Empfangsdatum, Link zur PDF und ein je Zeile aenderbarer Status (Offen /
In Bearbeitung / Erledigt). Die Daten kommen ueber zwei
Power-Automate-Flows aus einer SharePoint-Liste, die per E-Mail-Trigger
automatisch befuellt wird - siehe **[REKLAMATIONEN_SETUP.md](REKLAMATIONEN_SETUP.md)**
fuer die vollstaendige Einrichtung (Flows, SharePoint-Liste,
`secrets.toml`). Ohne diese Einrichtung zeigt der Reiter einen Hinweis
statt eines Fehlers.

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
andere Ladungstraeger), das Zusammenfuehren mehrerer Quelldateien sowie
den Abruf/Status-Update der Ausfallfracht-Reklamationen (mit
simulierten HTTP-Antworten, ohne echte Power-Automate-Verbindung) ab.

## Dateien

- `app.py` – Streamlit-Oberflaeche (Start-Seite + Reiter Ladelisten und
  Reklamationen).
- `ladeliste_logic.py` – reine Verarbeitungslogik fuer Ladelisten
  (Zusammenfuehren, LKW-Blaetter erzeugen, Validierung), UI-unabhaengig
  und per CLI nutzbar.
- `reklamation_logic.py` – Abruf/Status-Update der Ausfallfracht-
  Reklamationen ueber die Power-Automate-Flows, UI-unabhaengig.
- `REKLAMATIONEN_SETUP.md` – Einrichtung der Power-Automate-Flows +
  SharePoint fuer den Reklamationen-Reiter.
- `tests/test_ladeliste_logic.py`, `tests/test_reklamation_logic.py` –
  pytest-Tests.
- `requirements.txt` – Python-Abhaengigkeiten.
- `.streamlit/secrets.toml.example` – Vorlage fuer die (nicht
  eingecheckte) `secrets.toml` mit den Flow-URLs.
