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
A, B, C, D, E = 900000001, 900000002, 900000003, 900000004, 900000005  # DEMO-Artikel


def _bedarf(zeilen):
    """zeilen: (Norm-Nr, Tage ab Stichtag, offene Menge, Werk, Abladestelle[, Kunde])"""
    df = pd.DataFrame([
        {"Norm-Nr": z[0], "Ladedatum": ST + pd.Timedelta(days=z[1]), "Wunschtermin": ST + pd.Timedelta(days=z[1] + 2),
         "Bestellmenge": z[2], "Geliefert": 0, "Zugewiesen offen": 0,
         "Kunde": z[5] if len(z) > 5 else "DEMO Kunde", "Kurztext": f"DEMO {z[0]}",
         "Werk": z[3], "Abladestelle": z[4], "Lieferplan": 1, "Einteilung": i}
        for i, z in enumerate(zeilen)
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
        (A, -5, 150, "11", "102K4", "DEMO Kunde Nord"),   # Rueckstand
        (A, 3, 100, "11", "102K4", "DEMO Kunde Nord"),    # in der Reaktionszeit
        (A, 40, 200, "14", "403C7", "DEMO Kunde Süd"),    # spaeter
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


# --- Rechnung -------------------------------------------------------------------

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


def test_bestandsprognose_steigt_mit_zugang_faellt_mit_bedarf(beispiel):
    _, _, bericht = beispiel
    v = bericht["verlauf"][A]
    # Kategorie 0 = Bestand heute, 1 = nach Rueckstand, dann je Tag ab Stichtag + 1
    assert v["labels"][:2] == ["Bestand / Stok", f"bis / {ST:%d.%m.} dahil"]
    assert v["tage"][2] == ST + pd.Timedelta(days=1)
    assert v["bestand"][0] == 100                    # Bestand heute
    assert v["bestand"][1] == 100 - 150              # Rueckstand 150 abgezogen -> -50
    idx = {d: i for i, d in enumerate(v["tage"]) if d is not None}
    assert v["zulauf"][idx[ST + pd.Timedelta(days=2)]] == 50
    assert v["bestand"][idx[ST + pd.Timedelta(days=2)]] == 0          # NRI-DEMO-1: zurueck auf 0
    assert v["bestand"][idx[ST + pd.Timedelta(days=3)]] == -100       # Bedarf 100 -> -100
    assert v["bestand"][idx[ST + pd.Timedelta(days=30)]] == 0         # NRI-DEMO-2 +100
    assert v["bestand"][idx[ST + pd.Timedelta(days=40)]] == -200      # Bedarf 200
    assert v["bestand"][-1] == -200
    assert v["bestand_plus"][0] == 100 and v["fehl_minus"][1] == -50
    assert v["erster_fehltag"] == "sofort"
    assert len(v["labels"]) == 2 + 22 * 7            # bis zum Horizont, taeglich
    # B: Bestand 0, Rueckstand 80 -> sofort; C: erster Fehltag = Ladedatum in 5 Tagen
    assert bericht["verlauf"][B]["erster_fehltag"] == "sofort"
    assert bericht["verlauf"][C]["erster_fehltag"] == ST + pd.Timedelta(days=5)


def test_durchschnittsbedarf_reichweite_und_kunden(beispiel):
    _, _, bericht = beispiel
    basis = bericht["basis"]
    # Export deckt ST-5 .. ST+40 ab (D in 400 Tagen liegt ausserhalb des Horizonts)
    assert basis["von"] == ST - pd.Timedelta(days=5) and basis["bis"] == ST + pd.Timedelta(days=40)
    assert basis["wochen"] == pytest.approx(46 / 7)
    a = bericht["artikel"].set_index("Norm-Nr")
    assert a.loc[A, "Ø Woche"] == pytest.approx(450 / (46 / 7))
    assert a.loc[A, "Ø Monat"] == pytest.approx(450 / (46 / 7) * 52 / 12)
    assert a.loc[A, "Reichweite Wochen"] == pytest.approx((100 + 150) / (450 / (46 / 7)))
    assert a.loc[B, "Reichweite Wochen"] == 0
    kunden = bericht["kunden"][A]
    assert list(kunden["Kunde"]) == ["DEMO Kunde Nord", "DEMO Kunde Süd"]
    assert list(kunden["Bedarf"]) == [250, 200]
    assert kunden["Anteil"].sum() == pytest.approx(1.0)
    assert kunden["Ø Woche"].sum() == pytest.approx(a.loc[A, "Ø Woche"])


def test_dashboard_kennzahlen(beispiel):
    _, _, bericht = beispiel
    d = bericht["dashboard"]
    assert d["artikel"] == 3
    assert {s: d["je_stufe"][s]["anzahl"] for s in (1, 2, 3, 4)} == {1: 1, 2: 1, 3: 1, 4: 0}
    assert d["je_stufe"][1]["menge"] == 80 and d["je_stufe"][2]["menge"] == 50 and d["je_stufe"][3]["menge"] == 60
    assert d["fehlt_gesamt"] == 80 + 200 + 60
    assert d["nri_bericht"] == 2 and d["unterwegs_menge"] == 150
    assert sum(d["wochen_summen"]["bedarf"]) == 450 + 80 + 60
    kz = pb.kennzahlen(bericht)
    assert kz["je_stufe"][1] == 1 and kz["fehlt_gesamt"] == 340


# --- Excel ----------------------------------------------------------------------

def _excel(bericht, notizen=None, sprache="TR"):
    inhalt = pb.erstelle_bericht_datei(bericht, notizen, sprache)
    return inhalt, openpyxl.load_workbook(io.BytesIO(inhalt))


def _uebersicht_zeilen(ws):
    kopf = pb._finde_kopfzeile(ws)
    return kopf, {ws.cell(r, pb.U_NORM).value: r for r in range(kopf + 1, ws.max_row + 1)
                  if ws.cell(r, pb.U_NORM).value is not None}


def test_datei_blaetter_kacheln_und_kurzuebersicht(beispiel):
    _, _, bericht = beispiel
    _, wb = _excel(bericht)
    assert wb.sheetnames == [pb.BLATT_UEBERSICHT, pb.BLATT_DETAILS, pb.BLATT_WOCHEN, pb.BLATT_UNTERWEGS, pb.BLATT_DATEN]
    assert wb[pb.BLATT_DATEN].sheet_state == "hidden"
    ws = wb[pb.BLATT_UEBERSICHT]
    kopf, zeilen = _uebersicht_zeilen(ws)
    assert kopf == pb.UEBERSICHT_KOPFZEILE
    kopfzeile = [str(ws.cell(kopf, s).value) for s in range(1, len(pb.UEBERSICHT_SPALTEN) + 1)]
    assert kopfzeile[pb.U_NOTIZ_DISPO - 1].startswith("Notiz Dispo\nDispo notu")
    assert kopfzeile[pb.U_NOTIZ_PROD - 1].startswith("Notiz Produktion\nÜretim notu")
    assert kopfzeile[pb.U_DETAILS - 1].startswith("Details")
    assert any(k.startswith("Gedeckt bis 22 Wo.?") for k in kopfzeile)          # der eine Status
    assert any(k.startswith("Ältester Abruf (Liefertermin)") for k in kopfzeile)
    assert not any(k.startswith(("Dringlichkeit", "Bezeichnung", "Ø", "Reichweite")) for k in kopfzeile)
    # je Artikel drei Zeilen, dringendste zuerst
    assert list(zeilen) == [B, A, C]
    assert [zeilen[B], zeilen[A], zeilen[C]] == [pb.UEBERSICHT_ERSTE_ZEILE + k * pb.ZEILEN_JE_ARTIKEL for k in range(3)]
    spalte = {name: i for i, (name, _, _) in enumerate(pb.UEBERSICHT_SPALTEN, start=1)}
    za = zeilen[A]
    assert ws.cell(za, spalte["Bestand (nutzbar)"]).value == 100
    assert ws.cell(za, spalte["Rückstand + {tage} Tage"]).value == 250           # 150 Rueckstand + 100 in 3 Tagen
    assert ws.cell(za, spalte["Unterwegs"]).value == 150
    assert ws.cell(za, pb.U_NRI).value == "NRI-DEMO-1  ·  13.11.  ·  50"         # NRI untereinander, nach Ankunft
    assert ws.cell(za + 1, pb.U_NRI).value == "NRI-DEMO-2  ·  11.12.  ·  100"
    assert ws.cell(za, spalte["Gedeckt bis {wochen} Wo.?"]).value == "Nein / Hayır"
    assert ws.cell(za, spalte["Ältester Abruf (Liefertermin)"]).value == (ST - pd.Timedelta(days=3)).to_pydatetime()
    assert f"K{za}:K{za + 2}" in {str(m) for m in ws.merged_cells.ranges}           # Notiz ueber drei Zeilen
    # 👁 Details und Norm-Nr fuehren zur Detailkarte
    assert ws.cell(zeilen[B], pb.U_DETAILS).value == "👁 Details"
    for s in (pb.U_DETAILS, pb.U_NORM):
        assert ws.cell(zeilen[B], s).hyperlink.location.startswith(f"'{pb.BLATT_DETAILS}'!A")
    # Kacheln: Handlungsbedarf, Fehlt gesamt, Rueckstand + 14 Tage, Unterwegs, gedeckt
    assert str(ws.cell(4, 1).value).startswith("Handlungsbedarf") and ws.cell(5, 1).value == 3
    assert ws.cell(5, 4).value == 340
    assert ws.cell(5, 6).value == 80 + 250 + 60
    assert ws.cell(5, 8).value == 150 and ws.cell(5, 9).value == 0
    assert len(ws._charts) == 0
    assert ws.freeze_panes == f"D{pb.UEBERSICHT_ERSTE_ZEILE}"
    assert ws.sheet_view.showGridLines is False


def _karten(ws):
    """Norm-Nr -> Titelzeile der Detailkarte (Norm-Nr steht versteckt in der Notizzeile darunter)."""
    return {ws.cell(r, pb.DETAIL_NORM_SPALTE).value: r - 1 for r in range(pb.ERSTE_ZEILE, ws.max_row + 1)
            if ws.cell(r, pb.DETAIL_NORM_SPALTE).value}


def _zeile_mit(ws, spalte, text, von, bis=None):
    bis = bis or ws.max_row
    return next(r for r in range(von, bis + 1) if str(ws.cell(r, spalte).value or "").startswith(text))


def test_detailkarte_kennzahlen_zwei_diagramme_und_abrufe(beispiel):
    _, _, bericht = beispiel
    _, wb = _excel(bericht, {A: {"dispo": "Kunde akzeptiert 20.11.", "produktion": ""}}, "DE")
    ws = wb[pb.BLATT_DETAILS]
    titel = _karten(ws)
    assert list(titel) == [B, A, C]
    t = titel[A]
    assert str(ws.cell(t, 2).value).startswith("2.  900000001")
    assert ws.cell(t, 11).value == "Gedeckt bis 22 Wo.: Nein / Hayır"
    assert ws.cell(t, 14).hyperlink.location.startswith(f"'{pb.BLATT_UEBERSICHT}'!A")
    spiegel = ws.cell(t + 1, pb.DETAIL_NOTIZ_DISPO).value
    assert spiegel.startswith("=IF(") and pb.BLATT_UEBERSICHT in spiegel
    # zwei Diagramme je Artikel, fest in ihren Zellbereich gelegt (kein Ueberlappen)
    assert len(ws._charts) == 6
    karte_a = sorted((c.anchor._from.row + 1, c.anchor.to.row) for c in ws._charts
                     if titel[A] < c.anchor._from.row + 1 < titel[C])
    assert karte_a[0] == (t + 8, t + 7 + pb.DIAGRAMM_ZEILEN)
    assert karte_a[1][0] > karte_a[0][1] + 1
    assert all(c.anchor.to.col == pb._D_DIAGRAMM_BIS for c in ws._charts)           # endet vor der Tabelle rechts
    # Kennzahlen-Kacheln
    kacheln = {str(ws.cell(t + 3, s).value).split(" / ")[0]: ws.cell(t + 4, s).value for s in range(2, 16, 2)}
    assert kacheln["Bestand (nutzbar)"] == 100
    assert kacheln["Unterwegs (NRI)"] == 150
    assert kacheln["Rückstand + 14 Tage"] == 250
    assert kacheln["Fehlt gesamt"] == 200
    assert kacheln["Ø Bedarf je Woche"] == pytest.approx(450 / (46 / 7))
    assert kacheln["Erster Fehltag"] == "sofort / hemen"
    # rechts neben der Prognose: Bestand, NRI, Abrufe der naechsten 4 Wochen
    k, n, o = pb._D_PANEL, pb._D_PANEL + 3, pb._D_PANEL + 4
    verf = _zeile_mit(ws, k, "Verfügbar gesamt", t, titel[C])
    assert ws.cell(verf, n).value == 250
    assert ws.cell(_zeile_mit(ws, k, "NRI-DEMO-1", t, verf), n).value == 50
    kopf = _zeile_mit(ws, k, "Ladedatum", verf, titel[C])
    assert [ws.cell(kopf + i, n).value for i in (1, 2)] == [150, 100]               # Rueckstand, dann in 3 Tagen
    assert [ws.cell(kopf + i, o).value for i in (1, 2)] == [100, 0]                 # Rest
    assert ws.cell(kopf + 1, k).value == "sofort / hemen"
    summe = _zeile_mit(ws, k, "Summe 4 Wo.", kopf, titel[C])
    assert ws.cell(summe, k + 1).value.startswith("✓ gedeckt")
    assert ws.cell(summe, n).font.color.rgb.endswith("15803D")                       # gruen
    # B: nichts da -> ab der ersten Zeile rot, Summe rot "fehlt"
    tb = titel[B]
    kopf_b = _zeile_mit(ws, k, "Ladedatum", tb, titel[A])
    assert ws.cell(kopf_b + 1, n).font.color.rgb.endswith("DC2626")
    summe_b = _zeile_mit(ws, k, "Summe 4 Wo.", kopf_b, titel[A])
    assert ws.cell(summe_b, k + 1).value == "✗ fehlt / eksik 80"
    # Bedarf je Kunde unter den Diagrammen
    kunde = _zeile_mit(ws, 2, "DEMO Kunde Nord", t, titel[C])
    assert ws.cell(kunde, 5).value == pytest.approx(250 / 450)
    # Diagrammdaten: je Woche, Achsenpunkte in der gewaehlten Sprache
    wd = wb[pb.BLATT_DATEN]
    werte_a = [wd.cell(r, 1).value for r in range(1, wd.max_row + 1)]
    assert "Bestand" in werte_a and "Rückst." in werte_a and f"KW {ST.isocalendar()[1]}" in werte_a
    assert sorted(b.id for b in ws.row_breaks.brk) == [titel[A] - 1, titel[C] - 1]


def test_vorschlag_eingabefelder_und_formeln(beispiel):
    _, _, bericht = beispiel
    _, wb = _excel(bericht)
    ws = wb[pb.BLATT_DETAILS]
    titel = _karten(ws)
    erste = {n: _zeile_mit(ws, pb._EINGABE_DATUM, "Datum / Tarih", t) + 1 for n, t in titel.items()}
    for norm, datum, menge in ((A, ST + pd.Timedelta(days=40), 200), (B, ST, 80), (C, ST + pd.Timedelta(days=5), 60)):
        assert pd.Timestamp(ws.cell(erste[norm], pb._EINGABE_DATUM).value) == datum
        assert ws.cell(erste[norm], pb._EINGABE_MENGE).value == menge
        assert ws.cell(erste[norm] + 1, pb._EINGABE_MENGE).value is None
    assert "sofort" in ws.cell(erste[B], 13).value
    summe = ws.cell(erste[A] + pb.MAX_VORSCHLAEGE, pb._EINGABE_MENGE).value
    assert summe == f"=SUM(L{erste[A]}:L{erste[A] + pb.MAX_VORSCHLAEGE - 1})"
    assert "MIN(" in ws.cell(erste[A] + pb.MAX_VORSCHLAEGE + 1, pb._EINGABE_MENGE).value
    # Diagrammdaten je Woche: Zugang = SUMIFS ueber die gelben Felder zwischen von/bis, Bestand laufend
    wd = wb[pb.BLATT_DATEN]
    kopf = next(r for r in range(1, wd.max_row + 1) if wd.cell(r, 1).value == f"Artikel {A}") + 1
    bereich = f"'{pb.BLATT_DETAILS}'!$L${erste[A]}:$L${erste[A] + pb.MAX_VORSCHLAEGE - 1}"
    assert wd.cell(kopf + 1, pb._D_STAND).value == 100
    assert wd.cell(kopf + 2, pb._D_VORSCHLAG).value.startswith(f"=SUMIFS({bereich},")
    assert '"<"&G' in wd.cell(kopf + 2, pb._D_VORSCHLAG).value
    assert '">="&F' in wd.cell(kopf + 3, pb._D_VORSCHLAG).value
    assert wd.cell(kopf + 3, pb._D_STAND).value == f"=I{kopf + 2}+C{kopf + 3}+H{kopf + 3}-B{kopf + 3}"
    assert wb.calculation.fullCalcOnLoad


def test_wochenverlauf_verdichtet_die_tagesprognose(beispiel):
    _, _, bericht = beispiel
    v = bericht["verlauf"][A]
    w = pb.wochen_verlauf(v, ST, "DE")
    assert w["labels"][:2] == ["Bestand", "Rückst."] and w["labels"][2] == f"KW {ST.isocalendar()[1]}"
    assert sum(w["bedarf"]) == sum(v["bedarf"]) and sum(w["zulauf"]) == sum(v["zulauf"])
    assert w["bestand"][-1] == v["bestand"][-1] and w["bestand"][1] == v["bestand"][1]
    assert w["von"][2] == ST + pd.Timedelta(days=1) and w["bis"][1] == ST + pd.Timedelta(days=1)
    assert all(b == w["von"][i + 1] for i, b in enumerate(w["bis"][2:-1], start=2))   # Wochen lueckenlos


def test_nutzbarer_bestand_nach_fuellmenge(monkeypatch):
    # 970698000: Fuellmenge 1.000 je KLT (Almanca Hilfsdaten); je Charge auf volle KLT, OUT1 zaehlt nicht
    art = 970698000
    bedarf = _bedarf([(art, -1, 5000, "11", "106K4")])
    positionen, zugang, _ = _rechnen(bedarf, {art: 3300}, [(1, 30000, 1, "X")])
    charge = pd.DataFrame([
        {"Norm-Nr": art, "Menge": 2500, "Bestandsart": "F2", "Lagerort": "01A.01", "Charge": "C1"},
        {"Norm-Nr": art, "Menge": 800, "Bestandsart": "F2", "Lagerort": "01A.02", "Charge": "C2"},
        {"Norm-Nr": art, "Menge": 4000, "Bestandsart": "F2", "Lagerort": "OUT1", "Charge": "C3"},
    ])
    ohne = pb.berechne_bericht(positionen, zugang, ST)
    mit = pb.berechne_bericht(positionen, zugang, ST, bestand_je_charge=charge)
    assert ohne["artikel"].set_index("Norm-Nr").loc[art, "Bestand"] == 3300
    a = mit["artikel"].set_index("Norm-Nr").loc[art]
    assert a["Bestand"] == 2000 and a["Fehlt gesamt"] == 3000 and not a["Gedeckt"]


def test_vw_nr_einheitlich_und_aus_der_artikelliste():
    assert pb.vw_nr_schreibweise("N91196801") == "N   911 968 01"
    assert pb.vw_nr_schreibweise("-N---911-968-01") == "N   911 968 01"
    assert pb.vw_nr_schreibweise("N  91261601") == "N   912 616 01"
    assert pb.vw_nr_schreibweise("-WHT-009-542") == "WHT 009 542"
    assert pb.vw_nr_schreibweise("5QE915359E") == "5QE 915 359 E"
    assert pb.vw_nr_schreibweise("12345678") == "12345678"                      # unbekannt: bleibt
    assert pb.vw_nr(934702000) == "N   108 194 01"                               # aus "Almanca Hilfsdaten"
    assert pb.vw_nr(999999999, "", "-WHT-009-642") == "WHT 009 642"              # sonst Kundenmaterial


def test_handlungsbedarf_zuerst():
    # D: Rueckstand kommt nur spaeter (gedeckt), E: Engpass in 5 Tagen ohne Ware -> E zuerst
    bedarf = _bedarf([(D, -2, 50, "11", "X"), (E, 5, 40, "11", "Y")])
    _, _, bericht = _rechnen(bedarf, {D: 0, E: 0}, [(D, 3, 50, "NRI-DEMO-7")])
    a = bericht["artikel"]
    assert list(a["Norm-Nr"]) == [E, D]
    assert list(a["Gedeckt"]) == [False, True] and list(a["Stufe"]) == [3, 2]


def test_vorschlag_deckt_fehlmenge_zum_bedarfstermin(beispiel):
    _, _, bericht = beispiel
    v = bericht["vorschlag"]
    assert [(x["Datum"], x["Menge"], x["Sofort"]) for x in v[A]] == [(ST + pd.Timedelta(days=40), 200, False)]
    assert [(x["Datum"], x["Menge"], x["Sofort"]) for x in v[B]] == [(ST, 80, True)]   # Rueckstand -> sofort
    assert [(x["Datum"], x["Menge"]) for x in v[C]] == [(ST + pd.Timedelta(days=5), 60)]
    # A: Vorschlag deckt die Fehlmenge; die Delle davor bleibt (Ware unterwegs, kommt zu spaet)
    mit = pb.verlauf_mit_vorschlag(bericht["verlauf"][A], [(x["Datum"], x["Menge"]) for x in v[A]], ST)
    assert mit["ende"] == 0 and mit["tiefster"] == -100 and mit["erster_fehltag"] == "sofort"
    assert sum(mit["vorschlag"]) == 200
    # Eingabe vor dem Stichtag zaehlt zum Rueckstand, nach dem Horizont faellt sie weg
    mit = pb.verlauf_mit_vorschlag(bericht["verlauf"][B], [(ST - pd.Timedelta(days=3), 80),
                                                           (ST + pd.Timedelta(days=400), 999), (pd.NaT, 5)], ST)
    assert mit["bestand"][1] == 0 and mit["erster_fehltag"] is None and sum(mit["vorschlag"]) == 80


def test_vorschlag_buendelt_in_fenstern_und_rundet():
    zeilen = pd.DataFrame({
        "Ladedatum": [ST - pd.Timedelta(days=2)] + [ST + pd.Timedelta(days=7 * k) for k in range(1, 20)],
        "Fehlt": [87.0] + [1234.0] * 19,
    })
    v = pb.vorschlag_zugaenge(zeilen, ST)
    assert len(v) == pb.MAX_VORSCHLAEGE
    assert v[0]["Datum"] == ST and v[0]["Sofort"] and v[0]["Bedarf bis"] == ST + pd.Timedelta(days=7)
    assert v[0]["Fehlt"] == 87 + 1234 and v[0]["Menge"] == 1400                  # ab 1.000 auf 100 aufrunden
    assert v[1]["Datum"] == ST + pd.Timedelta(days=14) and v[1]["Fehlt"] == 2 * 1234
    assert v[-1]["Bedarf bis"] == ST + pd.Timedelta(days=7 * 19)                 # letzte Zeile nimmt den Rest
    assert sum(x["Fehlt"] for x in v) == 87 + 19 * 1234
    assert pb.vorschlag_zugaenge(pd.DataFrame({"Ladedatum": [ST], "Fehlt": [87.0]}), ST)[0]["Menge"] == 90
    assert pb.vorschlag_zugaenge(zeilen.assign(Fehlt=0.0), ST) == []


def test_notizen_roundtrip_mit_archiv_und_in_details_getippt(beispiel):
    _, _, bericht = beispiel
    notizen = {A: {"dispo": "D-Notiz A", "produktion": "P-Notiz A"},
               777: {"dispo": "alte Notiz", "produktion": ""}}       # Artikel nicht im Bericht
    inhalt, wb = _excel(bericht, notizen)
    assert pb.BLATT_ARCHIV in wb.sheetnames and wb.sheetnames[-1] == pb.BLATT_DATEN
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
    _, zeilen = _uebersicht_zeilen(ws2)
    assert ws2.cell(zeilen[C], pb.U_NOTIZ_PROD).value == "Versand 14.11. per LKW"
    assert ws2.cell(zeilen[A], pb.U_NOTIZ_DISPO).value == "D-Notiz A"


def test_unterwegs_listet_alle_zugaenge_mit_link(beispiel):
    positionen, zugang, _ = beispiel
    zugang = pd.concat([zugang, zugang.iloc[[0]].assign(**{"Norm-Nr": 123, "Referenz": "NRI-DEMO-9"})])
    bericht = pb.berechne_bericht(positionen, zugang, ST)
    _, wb = _excel(bericht)
    ws = wb[pb.BLATT_UNTERWEGS]
    zeilen = {ws.cell(r, 1).value: r for r in range(pb.ERSTE_ZEILE, ws.max_row + 1)}
    assert set(zeilen) == {"NRI-DEMO-1", "NRI-DEMO-2", "NRI-DEMO-9"}
    link = ws.cell(zeilen["NRI-DEMO-1"], 10).hyperlink.location
    assert link == f"'{pb.BLATT_UEBERSICHT}'!A{pb.UEBERSICHT_ERSTE_ZEILE + pb.ZEILEN_JE_ARTIKEL}"   # A hat Rang 2
    assert ws.cell(zeilen["NRI-DEMO-9"], 10).value is None


def test_ohne_zugaenge_und_ohne_bedarf():
    # logic.berechne braucht mindestens einen Zugang (Platzhalter weit in der Zukunft)
    positionen = _rechnen(_bedarf([(A, 1, 10, "11", "X")]), {A: 10}, [(1, 30000, 1, "X")])[0]
    leer = pb.berechne_bericht(positionen, None, ST)
    assert leer["artikel"].empty
    inhalt, wb = _excel(leer)
    assert wb.sheetnames[:2] == [pb.BLATT_UEBERSICHT, pb.BLATT_DETAILS]
    assert len(wb[pb.BLATT_UEBERSICHT]._charts) == 0
    assert pb.kennzahlen(leer)["artikel"] == 0
    assert pb.lese_notizen(inhalt) == {}
