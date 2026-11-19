"""Tests fuer die EDI-Veraenderung (edi_vergleich.py). DEMO-Daten: erfundene
Lieferplaene/Artikel, Spalten wie loaders.lade_bedarf sie liefert."""
import io
from urllib.parse import unquote

import openpyxl
import pandas as pd
import pytest

import edi_vergleich as ev
from dispo_dashboard import config

ST = pd.Timestamp("2026-11-10")
VORTAG = ST - pd.Timedelta(days=1)


def _bedarf(zeilen, werk="11"):
    """zeilen: (Lieferplan, Tage ab Stichtag (Ladedatum), Bestellmenge, Geliefert)"""
    return pd.DataFrame([
        {"Lieferplan": lp, "Norm-Nr": 900000000 + lp, "Kunde": "DEMO Kunde", "Werk": werk, "Abladestelle": "DEMO1",
         "Kundenmaterial": "-N---910-971-02", "Kurztext": "DEMO Schraube",
         "Ladedatum": ST + pd.Timedelta(days=t), "Wunschtermin": ST + pd.Timedelta(days=t + 1),
         "Bestellmenge": m, "Geliefert": g, "Einteilung": i}
        for i, (lp, t, m, g) in enumerate(zeilen)
    ])


@pytest.fixture
def ergebnis():
    alt = _bedarf([
        (1, -1, 3000, 0), (1, 2, 5000, 0), (1, 10, 4000, 0),   # Rueckstand versendet + Erhoehung am 12.11.
        (2, 5, 4000, 0), (2, 20, 2000, 0),                     # 15.11. -> 18.11., 30.11. reduziert
        (3, 15, 6000, 0),                                       # vorgezogen 25.11. -> 19.11.
        (4, 30, 1000, 0),                                       # Lieferplan entfaellt
        (6, 3, 1000, 0), (6, 40, 500, 0),                       # unveraendert
        (7, -2, 2000, 500), (7, 1, 3000, 0), (7, 6, 1000, 0),   # Rueckstand ganz + 11.11. teilweise versendet
        (8, 2, 700, 0), (8, 9, 900, 0),                         # 12.11. weg: vorab versendet oder gestrichen?
    ])
    neu = _bedarf([
        (1, 2, 8000, 0), (1, 10, 4000, 0),
        (2, 8, 4000, 0), (2, 20, 500, 0),
        (3, 9, 6000, 0),
        (5, 12, 2500, 0),                                       # neuer Lieferplan
        (6, 3, 1000, 0), (6, 40, 500, 0),
        (7, 1, 3000, 1200), (7, 6, 1000, 0),
        (8, 9, 900, 0),
    ])
    return ev.vergleiche(alt, neu, VORTAG, ST)


def _je_lp(ergebnis):
    e = ergebnis["ereignisse"]
    return {lp: sorted(zip(g["Kategorie"], g["Menge"])) for lp, g in e.groupby("Lieferplan")}


def test_jede_aenderung_wird_eingeordnet(ergebnis):
    je = _je_lp(ergebnis)
    assert je[1] == [("erhoehung", 3000), ("versendet", 3000)]       # nicht: 3.000 "verschoben"
    assert je[2] == [("reduziert", 1500), ("verschoben", 4000)]
    assert je[3] == [("vorgezogen", 6000)]
    assert je[4] == [("entfallen", 1000)]
    assert je[5] == [("neu", 2500)]
    assert 6 not in je                                                # unveraendert
    assert je[7] == [("unklar", 1200), ("versendet", 1500)]           # Teilversand von vorne
    assert je[8] == [("unklar", 700)]
    e = ergebnis["ereignisse"].set_index(["Lieferplan", "Kategorie"])
    assert e.loc[(2, "verschoben"), "Tage"] == 3 and e.loc[(3, "vorgezogen"), "Tage"] == -6
    assert e.loc[(1, "erhoehung"), "Text"] == "12.11.2026: +3.000 Stück (5.000 → 8.000)"
    assert e.loc[(3, "vorgezogen"), "Text"] == "6.000 Stück von 25.11.2026 auf 19.11.2026 (6 Tage früher)"
    z = ergebnis["zusammenfassung"]
    assert z["erhoehung"] == {"lieferplaene": 1, "menge": 3000} and z["neu"]["menge"] == 2500


def test_bewertung_und_reihenfolge(ergebnis):
    lp = ergebnis["lieferplaene"].set_index("Lieferplan")
    # ohne Fehlmenge: kurzfristig mehr/frueher = pruefen, sonst Info, nur versendet = ausgeblendet
    assert lp.loc[1, "Bewertung"] == "🟠 Prüfen" and lp.loc[3, "Bewertung"] == "🟠 Prüfen"
    assert lp.loc[2, "Bewertung"] == "🔵 Info" and lp.loc[4, "Bewertung"] == "🔵 Info"
    assert lp.loc[8, "Bewertung"] == "🔵 Info"                       # unklar: sichtbar, aber Info
    assert lp.loc[7, "Rang"] == 3
    assert list(ergebnis["lieferplaene"]["Rang"]) == sorted(ergebnis["lieferplaene"]["Rang"])
    assert lp.loc[1, "Mehr"] == 3000 and lp.loc[1, "Versendet"] == 3000 and lp.loc[2, "Weniger"] == 1500
    assert lp.loc[1, "Teil (Kunde)"] == "N 910 971 02"


def test_fehlmenge_macht_kurzfristige_erhoehung_rot():
    alt = _bedarf([(1, 2, 5000, 0), (2, 30, 1000, 0)])
    neu = _bedarf([(1, 2, 8000, 0), (2, 30, 3000, 0)])
    positionen = pd.DataFrame({"Lieferplan": [1, 2], "Ladedatum": [ST + pd.Timedelta(days=2), ST + pd.Timedelta(days=30)],
                               "Fehlmenge": [2500.0, 0.0]})
    reihen = ev.vergleiche(alt, neu, VORTAG, ST, positionen)["lieferplaene"]
    lp = reihen.set_index("Lieferplan")
    assert lp.loc[1, "Bewertung"] == "🔴 Handeln" and lp.loc[1, "Fehlmenge"] == 2500
    assert lp.loc[2, "Bewertung"] == "🔵 Info"                       # spaet und gedeckt
    assert list(reihen["Lieferplan"]) == [1, 2]


def test_gleicher_export_und_umdatierter_rueckstand_sind_keine_aenderung():
    alt = _bedarf([(1, -5, 3000, 1000), (1, 4, 2000, 0)])
    assert ev.vergleiche(alt, alt, VORTAG, ST)["ereignisse"].empty
    umdatiert = _bedarf([(1, -1, 3000, 1000), (1, 4, 2000, 0)])       # Rueckstand nur neu datiert
    assert ev.vergleiche(alt, umdatiert, VORTAG, ST)["ereignisse"].empty
    # Wareneingang beim Kunden: Bestellmenge und Geliefert sinken gleich -> offene Menge gleich
    eingang = _bedarf([(1, -5, 2000, 0), (1, 4, 2000, 0)])
    assert ev.vergleiche(alt, eingang, VORTAG, ST)["ereignisse"].empty


def test_nur_gemeinsamer_zeitraum_wird_verglichen():
    alt = _bedarf([(1, 10, 1000, 0), (2, 20, 500, 0)])
    neu = _bedarf([(1, 10, 1000, 0), (1, 21, 4000, 0), (2, 21, 500, 0)])   # neuer Export reicht einen Tag weiter
    e = ev.vergleiche(alt, neu, VORTAG, ST)
    assert e["grenze"] == ST + pd.Timedelta(days=20)
    assert _je_lp(e) == {2: [("verschoben", 500)]}                   # 4.000 am neuen letzten Tag: nicht bewertet
    assert e["ausserhalb"] == 4500


def test_mail_vorlage_mit_cc_betreff_und_liefertermin(ergebnis):
    m = ev.mail_entwurf(ergebnis, [1])
    assert m["cc"] == "Dispo@normgmbh.de" and m["an"] == ""
    assert m["betreff"] == "Abrufänderung DEMO Kunde – Teil N 910 971 02 – Erhöhung"
    assert "• Erhöhung: Liefertermin 13.11.2026 – 5.000 → 8.000 Stück (+3.000)" in m["text"]   # Ladedatum + 1 Tag
    assert "versendet" not in m["text"]
    assert "Lieferplan 1 · Werk 11 · Abladestelle DEMO1" in m["text"]
    assert m["mailto"].startswith("mailto:?cc=Dispo@normgmbh.de&subject=")
    body = unquote(m["mailto"].split("&body=")[1])
    assert body == m["text"].replace("\n", "\r\n")
    # nur weniger/spaeter -> Bitte um Bestaetigung, englische Vorlage
    m2 = ev.mail_entwurf(ergebnis, [2], "EN")
    assert m2["betreff"].startswith("Delivery schedule change DEMO Kunde")
    assert "Postponed: 4.000 pcs from 16.11.2026 to 19.11.2026 (3 days later)" in m2["text"]
    assert "Please confirm that the reduction or postponement is intended" in m2["text"]
    # nur versendet / unklar -> keine Mail
    assert ev.mail_entwurf(ergebnis, [7])["mailto"] == "" and ev.mail_entwurf(ergebnis, [8])["mailto"] == ""


def test_sammelmail_wird_fuer_den_link_gekuerzt():
    alt = _bedarf([(lp, 10, 1000, 0) for lp in range(1, 40)])
    neu = _bedarf([(lp, 10, 2000, 0) for lp in range(1, 40)])
    e = ev.vergleiche(alt, neu, VORTAG, ST)
    m = ev.mail_entwurf(e, list(e["lieferplaene"]["Lieferplan"]))
    assert m["betreff"] == "Abrufänderungen DEMO Kunde (11) – 39 Teile"
    assert m["gekuerzt"] and len(m["mailto"]) <= ev.MAILTO_MAX_ZEICHEN
    assert m["text"].count("• Erhöhung") == 39                       # voller Text zum Kopieren
    assert "weitere Änderungen" in unquote(m["mailto"])


def test_vortag_datei_wird_im_ordner_gefunden(tmp_path):
    kopf = list(config.BEDARF_SPALTEN)
    leer = pd.DataFrame([[None] * len(kopf)], columns=kopf)
    for name in ("EXPORT_20261106_090000.xlsx", "EXPORT_20261109_090000.xlsx", "EXPORT_20261110_090000.xlsx"):
        leer.to_excel(tmp_path / name, index=False)
    pd.DataFrame({"x": [1]}).to_excel(tmp_path / "EXPORT_20261109_120000.xlsx", index=False)   # kein Bedarf
    pfad, datum = ev.finde_vortag_datei(tmp_path, ST.date())
    assert pfad.name == "EXPORT_20261109_090000.xlsx" and str(datum) == "2026-11-09"
    assert ev.finde_vortag_datei(tmp_path, pd.Timestamp("2026-11-06").date()) is None
    assert ev.datum_aus_name("EXPORT_20261109_103016.xlsx") == pd.Timestamp("2026-11-09").date()


def test_excel_export(ergebnis):
    wb = openpyxl.load_workbook(io.BytesIO(ev.erstelle_excel(ergebnis)))
    assert wb.sheetnames == ["Je Lieferplan", "Alle Änderungen"]
    ws = wb["Je Lieferplan"]
    assert ws.cell(4, 1).value == "Bewertung"
    assert ws.max_row == 4 + len(ergebnis["lieferplaene"])
    assert wb["Alle Änderungen"].max_row == 4 + len(ergebnis["ereignisse"])
