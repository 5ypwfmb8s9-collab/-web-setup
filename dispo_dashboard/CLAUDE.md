# Dispo-Dashboard (Norm Fasteners) – Übergabe für Claude Code / VWAI

Ziel: Ein eigener Reiter in **VWAI** (firmeneigenes KI-Tool), der täglich aus SAP-Exporten zeigt,
welche Lieferplan-Einteilungen im Rückstand sind, wie weit der Bestand die Bedarfe deckt und wo
künftig Engpässe entstehen. Später: geplante Zugänge, EDI-Abrufvergleich (kumulative Abweichungen,
Terminverschiebungen) und Mailvorlagen an die Ansprechpartner je Kundenwerk.

Dieses Projekt wird **Schritt für Schritt** aufgebaut: jede SAP-Datei bekommt einen eigenen Loader.
Die Logik ist von der Oberfläche getrennt, damit sie in VWAI, Streamlit oder Excel gleich funktioniert.

## Aufbau

```
dispo_dashboard/
  config.py        Spaltenzuordnung der SAP-Exporte + Geschäftsregeln (nur hier ändern)
  loaders.py       Einlesen der Rohexporte -> saubere DataFrames (deutsche Spaltennamen)
  logic.py         Dispositionslogik (Offene Menge, Deckung, Fehlmenge, Status, Ampel)
  excel_report.py  Excel-Report mit echten Formeln
  run.py           Kommandozeile
```

Aufruf:

```
pip install pandas openpyxl
# Täglich: alle Exporte in einen Ordner legen – je Quelle wird automatisch die NEUESTE Datei genommen
python -m dispo_dashboard.run --ordner "P:/Dispo/SAP_Exporte"
# oder einzeln:
python -m dispo_dashboard.run --bedarf EXPORT_Bedarf.xlsx --bestand EXPORT_Bestand.xlsx --zugang ZMM1000.xlsx --stockreport 28.09_Stok_Raporu.xlsx
```

**Immer der aktuellste Stand:** Dateien werden über ihre Spalten erkannt (nicht über den Namen).
Datenstand je Datei: SAP-Name `EXPORT_JJJJMMTT_hhmmss` → sonst `TT.MM` am Namensanfang
(z. B. `28.09_Stok_Raporu.xlsx`) → sonst Änderungsdatum der Datei. Je Quelle gewinnt das neueste Datum.
Stichtag = Datum des neuesten Bedarfsexports. Die Übersicht zeigt den Datenstand jeder Quelle und
markiert Quellen, die älter als der Stichtag sind, als „veraltet“ (`QUELLE_VERALTET_TAGE` in config.py).

## Datenquellen (Stand: Schritt 4 von 6)

| # | Datei | Inhalt | Status |
|---|---|---|---|
| 1 | Bedarf | Lieferplan-Einteilungen je Kunde/Werk/Artikel (Excel, türkische Spalten) | ✅ |
| 2 | Bestand | EWM-Bestandsliste je Charge/Lagerplatz (Excel) | ✅ |
| 3 | Zugänge | Transporte zu uns, SAP-Report ZMM1000 (Excel) | ✅ |
| 4 | Stock Report | Reichweiten + Notizen des Versenders (nur Nebeninfo) | ✅ |
| 5 | EDI-Abrufe | Abrufhistorie für Kumulativ-Vergleich (aktueller + vorheriger Stand) | offen |
| 6 | Kontakte | Ansprechpartner + Mail je Kundenwerk | Liste im Excel-Reiter „Werke & Kontakte“ |

### 1. Bedarf – wichtige Spalten

| SAP-Spalte | Bedeutung |
|---|---|
| Muhatap tanımı | Werk (Kundenwerk) |
| Teslimat yeri | Abladestelle |
| Malı teslim alan | SAP-Schlüsselnummer des Kunden (Warenempfänger) |
| Ad 1 | Firma |
| Müşteri | 2er-Nr (gebündelte Schlüsselnummer für Orte) |
| SD belgesi / Termin satır no. | Lieferplan / Einteilung |
| Malzeme | Norm-Nr (Artikel) |
| Müşteri malzemesi | Artikelbezeichnung des Kunden |
| Mlz.hazıredim tarihi | Ladedatum |
| Termin Tarihi | Gewünschtes Lieferdatum |
| Sipariş miktarı | Bestellmenge |
| Teslimat Miktarı | Gelieferte Menge |
| Açık Teyit | Zugewiesene Menge (offen) |
| İhtiyaç | Offene, noch zu versendende Menge (= Sipariş − Teslimat) |
| Kalan | Ungedeckt (= İhtiyaç − Açık Teyit) |

Die Spalte „Toplam Stok“ im Bedarfsexport wird **nicht** genutzt – Bestand kommt aus Datei 2.

### 2. Bestand – Regeln

| Stok türü | Bedeutung | Behandlung |
|---|---|---|
| F2 | Frei verwendbar | zählt als verfügbar |
| F1 | Angekommen, noch nicht eingelagert | zählt als verfügbar |
| K2 | Gesperrt | nur Info, wird nicht gerechnet |
| alle anderen (z. B. D2) | – | ignoriert |

Die erste Zeile des Exports ist eine SAP-Summenzeile (ohne Artikel) und wird verworfen.
Materialnummern kommen im Bestand als Text, im Bedarf als Zahl – `loaders.materialnr()` vereinheitlicht.

### 3. Zugänge (ZMM1000) – wichtige Spalten

| SAP-Spalte | Bedeutung |
|---|---|
| Nakliye numarası | Transportnummer |
| Referans | Referenznummer der Lieferung zu uns |
| Ad 1 | Spediteur |
| Teslimat / Referans belge | Lieferung / Referenzbeleg |
| Malzeme | Norm-Nr (Artikel) |
| Plnln.nakliye sonu | Geplante Ankunft bei uns |
| Teslimat miktarı | Menge |

Je Lieferung gibt es Hauptpositionen (Menge 0) und Chargen-Unterpositionen (Kalem ≥ 900000) mit den
echten Mengen – Summieren ist daher korrekt, nichts wird doppelt gezählt. `lade_zugang` fasst Chargen je
Transport/Lieferung/Artikel zusammen und entfernt Nullzeilen.
Zugänge mit geplanter Ankunft vor dem Stichtag sind noch nicht empfangen und zählen ab Stichtag
(„Ankunft überfällig“). Achtung Doppelzählung: Sobald ein Zugang als F1 im Bestand steht, darf er
nicht mehr in ZMM1000 auftauchen – bei Auffälligkeiten prüfen.

### 4. Stock Report des Versenders – NUR NEBENINFO

Blatt `Format`, Kopfzeile in Zeile 2 (Blatt `Sayfa1` wird ignoriert). Geht **nicht** in die Deckungsrechnung
ein – die Mengen dort sind keine Zugänge. Angezeigt werden Reichweite, freier Bestand beim Versender,
„Yolda“ laut Report, Salden 2–12 Wochen, Verantwortlicher, Kundengruppe und die **neueste Notiz**.

| SAP-Spalte | Bedeutung |
|---|---|
| Stok yeterliği | Reichweite laut Report (Einheit noch offen, daher neutral beschriftet) |
| Tahditsiz klnb. | Frei verwendbar beim Versender |
| Yolda | Unterwegs laut Report (nur Info) |
| 2Hafta … 12Hafta | Saldo nach 2 … 12 Wochen (2-Wochen-Schritte über 12 Wochen) |
| Lojistik Temsilcisi | Verantwortliche Person |
| Müşteri Grubu | Kundengruppe |

Rechts von „Müşteri Grubu“ stehen inoffizielle Notizspalten, neueste links („28.09 notlar“, „21.09 notlar –
toplantı“, …). Je Artikel wird die erste nicht leere Notiz (nicht „0“) mit ihrem Datum übernommen.
Im Excel: eigener Reiter „Stock Report (Info)“ sowie graue Info-Spalten in „Deckung je Artikel“ und „Rückstand“.

## Geschäftsregeln

- **Offene Menge** = Bestellmenge − Geliefert
- **Deckung**: Je Artikel werden Bestand + Zugänge, die bis zum Ladedatum ankommen, in Reihenfolge des
  Ladedatums auf die offenen Einteilungen verteilt (kumulierter Bedarf). Was fehlt, ist **Fehlmenge**.
- **Gedeckt ab**: Ankunftsdatum des Zugangs, mit dem die Fehlmenge gedeckt wäre;
  **Verspätung** = Gedeckt ab − Ladedatum
- **Rückstand** = Ladedatum < Stichtag und offene Menge > 0
- **Status je Einteilung**: Erledigt / Rückstand gedeckt (nur versenden) / Rückstand, Zugang kommt /
  Rückstand ungedeckt / Gedeckt / Zugang zu spät / Engpass (kein Zugang, im Rot-Horizont) / Fehlmenge später
- **Ampel je Artikel**: Rot = erste Fehlmenge ≤ 14 Tage (oder überfällig), Gelb ≤ 30 Tage, sonst Grün
- Horizonte in `config.py`

## Integration in VWAI (nächster Schritt mit Claude Code)

Vor dem Umsetzen in der VWAI-Umgebung klären:

1. Wie werden in VWAI neue Reiter angelegt (Python/Streamlit, Web-Frontend, Plugin)?
2. Wo landen die täglichen SAP-Exporte (Netzlaufwerk, Upload, Schnittstelle)?
3. Darf VWAI Mails versenden oder nur Entwürfe (mailto/Outlook) erzeugen?

Empfehlung: Den Datenabzug als festen, geplanten Job laufen lassen (nicht durch die KI),
`loaders` + `logic` unverändert übernehmen und im VWAI-Reiter nur die Anzeige bauen
(Kennzahlen, Rückstand, Deckung/Ampel, Bedarf je Woche, später EDI und Mail).
Die KI in VWAI eignet sich für Erklärungen, Priorisierung und Mailtexte.

## Arbeitsregeln für Claude Code

- **Rechenlogik nicht ändern ohne Rückfrage.** `loaders.py`, `logic.py` und die Regeln in `config.py`
  wurden mit dem Disponenten abgestimmt. Neue Anforderungen = neue Funktionen, nicht Umbau der alten.
- **Vor und nach jeder Änderung den Regressionstest laufen lassen:**
  `pytest dispo_dashboard/tests` oder `python -m dispo_dashboard.tests.test_dispo_regression`
  (Testdaten: `dispo_testdaten/`, Stichtag 06.10.2026). Werte im Test nur ändern, wenn eine Regeländerung
  bewusst beschlossen wurde.
- **Excel-Report und Python-Logik müssen identisch rechnen.** Wird eine Regel geändert, beide Stellen
  anpassen (`logic.py` und die Formeln in `excel_report.py`) und vergleichen.
- **Neue SAP-Exporte** (als Nächstes EDI-Abrufe mit aktuellem + vorherigem Stand, dann Kontakte):
  Spaltenzuordnung in `config.py`, eigener Loader in `loaders.py`, Erkennung in `loaders.dateityp`,
  Test ergänzen. Spaltennamen der Exporte sind türkisch; Bedeutung beim Nutzer erfragen.
- **Kundendaten nicht committen.** `dispo_testdaten/` und `beispiel_ausgabe/` enthalten echte Exporte und
  sind per `.gitignore` ausgeschlossen.
- Der Nutzer ist Disponent, kein Entwickler: Schritte kurz erklären, Ergebnis zeigen, dann den nächsten Schritt.

## Offene Punkte

- Einheit von „Stok yeterliği“ im Stock Report (Wochen oder Tage?)
- F1-Bestand kam im ersten Bestandsexport nicht vor – prüfen, ob Filter/Lagertyp fehlt
- 21 Artikel mit Bedarf, aber ohne Bestand (15 fehlen ganz im Bestandsexport) – prüfen
- Puffer zwischen Ankunft und Ladedatum? Aktuell zählt ein Zugang, wenn er spätestens am Ladedatum ankommt
