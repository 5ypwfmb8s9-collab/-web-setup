"""Tests fuer den Bericht an die Produktion (produktionsbericht.py).
DEMO-Daten: erfundene Artikel/NRI, Eingabe laeuft durch logic.berechne wie im
Dashboard, damit die Spalten (Kum. Bedarf, Fehlmenge ...) echt sind."""
import io

import openpyxl
import pandas as pd
import pytest

import produktionsbericht as pb
from dispo_dashboard import logic

ST = pd.Timestamp("2026-11-11")
A, B, C, D = 900000001, 900000002, 900000003, 900000004  # DEMO-Artikel


def _bedarf(zeilen):
    """zeilen: (Norm-Nr, Tage ab Stichtag, offene Menge, Werk, Abladestelle)"""
    df = pd.DataFrame([
        {"Norm-Nr": n, "Ladedatum": ST + pd.Timedelta(days=t), "Wunschtermin": ST + pd.Timedelta(days=t + 2),
         "Bestellmenge": m, "Geliefert": 0, "Zugewiesen offen": 0, "Kunde": "DEMO Kunde", "Kurztext": f"DEMO {n}",
         "Werk": w, "Abladestelle": ab, "Lieferplan": 1, "Einteilung": i}
        for i, (n, t, m, w, ab) in enumerate(zeilen)
    ])
    return df.sort_values(["Norm-Nr", "Ladedatum", "Einteilung"]).reset_index(drop=True)


def _rechnen(bedarf, bestand: dict, zugaenge, **kwargs):
    """zugaenge: (Norm-Nr, Tage ab Stichtag, Menge, NRI)"""
    bestand_artikel = pd.DataFrame({"Norm-Nr": list(bestand), "Verfügbar": list(bestand.values())})
    zugang = pd.DataFrame([
        {"Norm-Nr": n, "Geplante Ankunft": ST + pd.Timedelta(days=t), "Menge": m, "Referenz": nri,
         "Transport": "DEMO-T", "Spediteur": "DEMO Spedition", "Lieferung": 1, "Referenzbeleg": 1}
        for n, t, m, nri in zugaenge
    ], columns=["Norm-Nr", "Geplante Ankunft", "Menge", "Referenz", "Transport", "Spediteur", "Lieferung", "Referenzbeleg"])
    positionen, _, zugang_vorbereitet = logic.berechne(bedarf, bestand_artikel, zugang, ST)
    return positionen, zugang_vorbereitet, pb.berechne_bericht(positionen, zugang_vorbereitet, ST, **kwargs)


@pytest.fixture
def beispiel():
    bedarf = _bedarf([
        (A, -5, 150, "11", "102K4"),   # Rueckstand
        (A, 3, 100, "11", "102K4"),    # in der Reaktionszeit
        (A, 40, 200, "11", "102K4"),   # spaeter
        (B, -2, 80, "14", "403C7"),    # Rueckstand, nichts da
        (C, 5, 60, "21", "601A0"),     # Engpass in 5 Tagen
        (D, 2, 10, "22", "001N0"),     # voll durch Bestand gedeckt
        (D, 400, 999, "22", "001N0"),  # jenseits des Horizonts
    ])
    zugaenge = [
        (A, 2, 50, "NRI-DEMO-1"),      # kommt nach dem Rueckstands-Ladedatum
        (A, 30, 100, "NRI-DEMO-2"),    # kommt nach der Einteilung in 3 Tagen
    ]
    return _rechnen(bedarf, {A: 100, B: 0, C: 0, D: 50}, zugaenge)


def test_deckung_je_einteilung_bestand_nri_fehlt(beispiel):
    _, _, bericht = beispiel
    z = bericht["zeilen"].set_index(["Norm-Nr", "Bereich"])
    rueck = z.loc[(A, "rueckstand")]
    assert (rueck["Aus Bestand"], rueck["Spaet"], rueck["Fehlt"]) == (100, 50, 0)
    assert rueck["Quellen spaet"] == [("NRI-DEMO-1", ST + pd.Timedelta(days=2), 50)]
    kurz = z.loc[(A, "kurz")]
    assert (kurz["Rechtzeitig"], kurz["Spaet"], kurz["Fehlt"]) == (0, 100, 0)
    lang = z.loc[(A, "lang")]
    assert lang["Fehlt"] == 200


def test_spaet_plus_fehlt_ist_fehlmenge_aus_logic(beispiel):
    positionen, zugang, _ = beispiel
    alle = pb.berechne_bericht(positionen, zugang, ST, gedeckte_aufnehmen=True)["zeilen"].set_index("Position")
    assert ((alle["Spaet"] + alle["Fehlt"]) - positionen.loc[alle.index, "Fehlmenge"]).abs().max() == 0
    assert ((alle["Rechtzeitig"] + alle["Spaet"] + alle["Fehlt"]) - alle["Offen"]).abs().max() == 0


def test_reihenfolge_rueckstand_fehlt_vor_unterwegs_vor_engpass(beispiel):
    _, _, bericht = beispiel
    a = bericht["artikel"]
    assert list(a["Norm-Nr"]) == [B, A, C]       # D voll gedeckt -> nicht im Bericht
    assert list(a["Stufe"]) == [1, 2, 3]
    assert list(a["Rang"]) == [1, 2, 3]
    zeile_a = a.set_index("Norm-Nr").loc[A]
    assert zeile_a["Rückstand später"] == 50 and zeile_a["Kurz später"] == 100 and zeile_a["Später fehlt"] == 200


def test_gedeckte_auf_wunsch_und_horizont(beispiel):
    positionen, zugang, _ = beispiel
    bericht = pb.berechne_bericht(positionen, zugang, ST, gedeckte_aufnehmen=True)
    a = bericht["artikel"].set_index("Norm-Nr")
    assert a.loc[D, "Stufe"] == 5
    assert a.loc[D, "Bedarf Horizont"] == 10        # Einteilung in 400 Tagen faellt raus
    kurz = pb.berechne_bericht(positionen, zugang, ST, reaktion_tage=2)
    assert kurz["artikel"].set_index("Norm-Nr").loc[C, "Stufe"] == 4  # 5 Tage > 2 Tage Reaktionszeit


def test_wochenraster_summiert_bedarf_und_zulauf(beispiel):
    _, _, bericht = beispiel
    werte = bericht["matrix"][A]
    assert sum(werte["bedarf"]) == 450
    assert sum(werte["zulauf"]) == 150
    assert werte["bedarf"][0] == 150                 # Rueckstand-Spalte (bis Stichtag)
    assert sum(werte["fehlt"]) == 200


def _excel(bericht, notizen=None, sprache="TR"):
    inhalt = pb.erstelle_bericht_datei(bericht, notizen, sprache)
    return inhalt, openpyxl.load_workbook(io.BytesIO(inhalt))


def test_datei_blaetter_kopf_und_reihenfolge(beispiel):
    _, _, bericht = beispiel
    _, wb = _excel(bericht)
    assert wb.sheetnames == [pb.BLATT_UEBERSICHT, pb.BLATT_DETAILS, pb.BLATT_WOCHEN, pb.BLATT_UNTERWEGS]
    ws = wb[pb.BLATT_UEBERSICHT]
    kopf = [str(ws.cell(pb.KOPFZEILE, s).value) for s in range(1, len(pb.UEBERSICHT_SPALTEN) + 1)]
    assert kopf[pb.U_NOTIZ_DISPO - 1].startswith("Notiz Dispo\nDispo notu")
    assert kopf[pb.U_NOTIZ_PROD - 1].startswith("Notiz Produktion\nÜretim notu")
    norms = [ws.cell(r, pb.U_NORM).value for r in range(pb.ERSTE_ZEILE, pb.ERSTE_ZEILE + 3)]
    assert norms == [B, A, C]
    assert ws.cell(pb.ERSTE_ZEILE, 2).value.startswith("Rückstand – fehlt\nGecikme – eksik")
    # Link von der Norm-Nr zum Detailblock
    assert ws.cell(pb.ERSTE_ZEILE, pb.U_NORM).hyperlink.location.startswith(f"'{pb.BLATT_DETAILS}'!A")


def test_details_hinweise_und_notiz_spiegel(beispiel):
    _, _, bericht = beispiel
    _, wb = _excel(bericht, {A: {"dispo": "Kunde akzeptiert 20.11.", "produktion": ""}}, "DE")
    ws = wb[pb.BLATT_DETAILS]
    titel = {ws.cell(r, pb.DETAIL_NORM_SPALTE).value: r for r in range(pb.ERSTE_ZEILE, ws.max_row + 1)
             if ws.cell(r, pb.DETAIL_NORM_SPALTE).value}
    assert list(titel) == [B, A, C]
    spiegel = ws.cell(titel[A], pb.DETAIL_NOTIZ_DISPO).value
    assert spiegel.startswith("=IF(") and pb.BLATT_UEBERSICHT in spiegel
    texte = [str(ws.cell(r, 9).value or "") for r in range(titel[A], titel[C])]
    assert any("NRI-DEMO-1" in t and "7 T. zu spät" in t for t in texte)
    assert any(t.startswith("fehlt 80 – überfällig") for t in
               (str(ws.cell(r, 9).value or "") for r in range(titel[B], titel[A])))


def test_notizen_roundtrip_mit_archiv_und_in_details_getippt(beispiel):
    _, _, bericht = beispiel
    notizen = {A: {"dispo": "D-Notiz A", "produktion": "P-Notiz A"},
               777: {"dispo": "alte Notiz", "produktion": ""}}       # Artikel nicht im Bericht
    inhalt, wb = _excel(bericht, notizen)
    assert pb.BLATT_ARCHIV in wb.sheetnames
    # Produktion tippt (versehentlich) direkt im Detailblock von C
    ws = wb[pb.BLATT_DETAILS]
    zeile_c = next(r for r in range(pb.ERSTE_ZEILE, ws.max_row + 1) if ws.cell(r, pb.DETAIL_NORM_SPALTE).value == C)
    ws.cell(zeile_c, pb.DETAIL_NOTIZ_PROD, value="Versand 14.11. per LKW")
    puffer = io.BytesIO()
    wb.save(puffer)
    gelesen = pb.lese_notizen(puffer.getvalue())
    assert gelesen[A] == {"dispo": "D-Notiz A", "produktion": "P-Notiz A"}
    assert gelesen[777]["dispo"] == "alte Notiz"
    assert gelesen[C]["produktion"] == "Versand 14.11. per LKW"
    # neuer Bericht: Notizen stehen wieder in der Uebersicht
    _, wb2 = _excel(bericht, gelesen)
    ws2 = wb2[pb.BLATT_UEBERSICHT]
    zeilen = {ws2.cell(r, pb.U_NORM).value: r for r in range(pb.ERSTE_ZEILE, ws2.max_row + 1)}
    assert ws2.cell(zeilen[C], pb.U_NOTIZ_PROD).value == "Versand 14.11. per LKW"
    assert ws2.cell(zeilen[A], pb.U_NOTIZ_DISPO).value == "D-Notiz A"


def test_unterwegs_listet_alle_zugaenge(beispiel):
    positionen, zugang, _ = beispiel
    zugang = pd.concat([zugang, zugang.iloc[[0]].assign(**{"Norm-Nr": 123, "Referenz": "NRI-DEMO-9"})])
    bericht = pb.berechne_bericht(positionen, zugang, ST)
    _, wb = _excel(bericht)
    ws = wb[pb.BLATT_UNTERWEGS]
    nri = [ws.cell(r, 1).value for r in range(pb.ERSTE_ZEILE, ws.max_row + 1)]
    assert set(nri) == {"NRI-DEMO-1", "NRI-DEMO-2", "NRI-DEMO-9"}


def test_ohne_zugaenge_und_ohne_bedarf():
    # logic.berechne braucht mindestens einen Zugang (Platzhalter weit in der Zukunft)
    positionen = _rechnen(_bedarf([(A, 1, 10, "11", "X")]), {A: 10}, [(1, 30000, 1, "X")])[0]
    leer = pb.berechne_bericht(positionen, None, ST)
    assert leer["artikel"].empty
    inhalt, wb = _excel(leer)
    assert wb.sheetnames[:2] == [pb.BLATT_UEBERSICHT, pb.BLATT_DETAILS]
    assert pb.kennzahlen(leer)["artikel"] == 0
