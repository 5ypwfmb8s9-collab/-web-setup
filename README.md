# Ladelisten-Tool

Automatisiertes Tool zur Verarbeitung von Excel-Ladelisten: Datei(en)
hochladen, die Verarbeitung laeuft automatisch, am Ende steht die fertige
`.xlsx`-Datei zum Download bereit.

## Ablauf

1. Eine oder mehrere Excel-Dateien mit dem Blatt **"Avis Lade Listen"**
   hochladen (Zeile 1 = Ueberschriften, Daten ab Zeile 2, identische
   Spaltenstruktur in allen Dateien).
2. Alle Dateien werden zu einem gemeinsamen Datensatz zusammengefuehrt
   (Reihenfolge bleibt erhalten, keine Sortierung/Deduplizierung) und
   unveraendert als Blatt "Avis Lade Listen" in die Ausgabe geschrieben.
3. Fuer jeden eindeutigen Wert in Spalte L ("LKW VL") wird ein eigenes
   Blatt "LKW &lt;Wert&gt;" mit den zugehoerigen Positionen, Summenformeln,
   Bestaetigungs- und Unterschriftsbereich sowie Druckeinstellungen erzeugt.
4. Automatisierte Validierungen pruefen das Ergebnis (Zuordnung,
   Reihenfolge, Summen, Layout, Druckbereich). Schlaegt eine Pruefung fehl,
   wird keine Datei zum Download angeboten.

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
andere Ladungstraeger) sowie das Zusammenfuehren mehrerer Quelldateien ab.

## Dateien

- `app.py` – Streamlit-Oberflaeche (Upload, automatische Verarbeitung,
  Zusammenfassung, Validierung, Download).
- `ladeliste_logic.py` – reine Verarbeitungslogik (Zusammenfuehren,
  LKW-Blaetter erzeugen, Validierung), UI-unabhaengig und per CLI nutzbar.
- `tests/test_ladeliste_logic.py` – pytest-Tests.
- `requirements.txt` – Python-Abhaengigkeiten.
