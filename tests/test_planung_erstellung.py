"""Tests fuer Planung Erstellung: Rueckstand-Sortierung, Markierung
eingeplanter Rueckstaende, Bereich "Zugang erwartet" und Vorziehen in eine
bestehende Planung. Synthetische Daten, Artikel ohne Fuellmengen-Eintrag
(Fuellmenge 1 -> Packeinheiten = Menge), Standard-Palette 10/10."""
import io

import openpyxl
import pandas as pd
import pytest

import planung_erstellung as pe

STICHTAG = pd.Timestamp("2026-11-03")
PLANUNG = pd.Timestamp("2026-11-06")
A_ALT, A_NEU, A_ERW, A_NIX = 999000001, 999000002, 999000003, 999000004


def _positionen(zeilen):
    df = pd.DataFrame(zeilen, columns=["Norm-Nr", "Abladestelle", "Ladedatum", "Offene Menge"])
    df["Ladedatum"] = pd.to_datetime(df["Ladedatum"])
    df = df.sort_values(["Norm-Nr", "Ladedatum"]).reset_index(drop=True)
    df["Kum. Bedarf Artikel"] = df.groupby("Norm-Nr")["Offene Menge"].cumsum()
    df["Bestand verfügbar"] = 0
    df["VW-Nr"] = "N 1"
    return df


def _bestand(mengen: dict):
    return pd.DataFrame(
        [{"Norm-Nr": n, "Menge": m, "Bestandsart": "F2", "Lagerort": "01A.01", "Charge": f"C{n}"}
         for n, m in mengen.items()]
    )


def _zugang(zeilen):
    return pd.DataFrame(zeilen, columns=["Norm-Nr", "Referenz", "Ankunft gerechnet", "Menge"]).assign(
        **{"Ankunft gerechnet": lambda d: pd.to_datetime(d["Ankunft gerechnet"])}
    )


@pytest.fixture
def daten():
    positionen = _positionen([
        (A_ALT, "20A", "2026-10-20", 30),   # Rueckstand, Ware jetzt da
        (A_NEU, "10B", "2026-11-05", 20),   # normal, nicht Rueckstand
        (A_ERW, "05C", "2026-10-28", 25),   # Rueckstand, NRI kommt 06.11.
        (A_NIX, "05C", "2026-10-15", 12),   # Rueckstand, NRI erst 20.11.
        (A_NIX, "01D", "2026-10-30", 8),
    ])
    bestand = _bestand({A_ALT: 30, A_NEU: 20})
    zugang = _zugang([
        (A_ERW, "NRI2026000000001", "2026-11-06", 40),
        (A_NIX, "NRI2026000000002", "2026-11-20", 50),
    ])
    return positionen, bestand, zugang


def _erstelle(daten):
    positionen, bestand, zugang = daten
    inhalt, kennzahlen, rueck = pe.erstelle_planungsdatei(positionen, bestand, zugang, PLANUNG, stichtag=STICHTAG)
    return openpyxl.load_workbook(io.BytesIO(inhalt)), kennzahlen, rueck


def _zeilen(ws):
    return {ws.cell(row=r, column=7).value: r for r in pe._belegte_zeilen(ws)}


def test_rueckstaende_artikelweise_sortiert(daten):
    wb, _, rueck = _erstelle(daten)
    assert list(rueck["Norm-Nr"]) == sorted(rueck["Norm-Nr"])
    nix = rueck[rueck["Norm-Nr"] == A_NIX]
    assert list(nix["Abladestelle"]) == ["05C", "01D"]  # je Artikel aeltestes Ladedatum zuerst
    ws = wb["Rückstände"]
    norm = [ws.cell(row=r, column=7).value for r in range(5, 12)]
    assert norm == [A_ERW, None, A_NIX, A_NIX, None, None, None]


def test_eingeplanter_rueckstand_markiert(daten):
    wb, kennzahlen, _ = _erstelle(daten)
    ws = wb["Almanca"]
    zeilen = _zeilen(ws)
    alt, neu = zeilen[A_ALT], zeilen[A_NEU]
    assert ws.cell(row=alt, column=6).font.color.rgb == pe.ROT
    assert ws.cell(row=alt, column=12).value.date() == pd.Timestamp("2026-10-20").date()
    assert ws.cell(row=alt, column=12).number_format == "DD.MM.YYYY"
    assert ws.cell(row=neu, column=12).value is None
    assert not (ws.cell(row=neu, column=6).font.color and ws.cell(row=neu, column=6).font.color.rgb == pe.ROT)
    assert kennzahlen["rueckstand_eingeplant"] == 1


def test_eintreffende_rueckstaende_gelb_im_blatt_rueckstaende(daten):
    wb, kennzahlen, rueck = _erstelle(daten)
    alm = wb["Almanca"]
    assert A_ERW not in _zeilen(alm)  # nicht in der Planung
    assert alm["E2"].value == "=SUM(Q5:Q624)" and alm["H2"].value == "=SUM(T5:T624)"
    ws = wb["Rückstände"]
    zeilen = _zeilen(ws)
    erw, nix = zeilen[A_ERW], zeilen[A_NIX]
    for spalte in range(1, 21):
        assert ws.cell(row=erw, column=spalte).fill.fgColor.rgb == "FFFFFF00"
    assert ws.cell(row=erw, column=21).fill.fgColor.rgb != "FFFFFF00"
    assert "NRI2026000000001" in ws.cell(row=erw, column=13).value
    assert ws.cell(row=nix, column=1).fill.fgColor.rgb != "FFFFFF00"  # NRI erst nach Planungsdatum
    assert kennzahlen["erwartet_zeilen"] == 1
    assert rueck.loc[rueck["Norm-Nr"] == A_ERW, "Eintreffend bis Planung"].iloc[0] == 25


def test_eintreffende_menge_nach_dringlichkeit_und_nur_genutzte_nri():
    rueck = pe._rueckstand_anzeige(
        _positionen([(A_NIX, "05C", "2026-10-15", 12), (A_NIX, "01D", "2026-10-30", 8)]), {}
    )
    zugang = _zugang([(A_NIX, "NRI1", "2026-11-04", 12), (A_NIX, "NRI2", "2026-11-05", 1)])
    df = pe._markiere_eintreffende(rueck, zugang, PLANUNG).set_index("Abladestelle")
    assert df.loc["05C", "Eintreffend bis Planung"] == 12
    assert df.loc["05C", "Zugang Info"].startswith("NRI1") and "NRI2" not in df.loc["05C", "Zugang Info"]
    assert df.loc["01D", "Eintreffend bis Planung"] == 1
    assert df.loc["01D", "Zugang Info"].startswith("NRI2")


# --- Paletten / Mix-Paletten -------------------------------------------------

def _gruppe(zeilen):
    return pd.DataFrame(
        [{"Norm-Nr": n, "Packeinheiten": k, "Fuellmenge": f, "Menge": k * f, "Menge_gerundet": g}
         for n, k, f, g in zeilen]
    )


@pytest.fixture
def spez(monkeypatch):
    tabelle = {}
    monkeypatch.setattr(pe, "_PALETTENSPEZIFIKATION", tabelle)
    return tabelle


def test_angefangene_lage_unter_5_klt_kommt_zu_dhl_ups(spez):
    # Beispiel 307M7: 930730000, 11 KLT, 10 je Lage / 30 je Palette
    spez[("307M7", 930730000)] = {"anzahl_pro_lage": 10, "anzahl_volle_palette": 30, "typ": 111444}
    plan, dhl = pe._plane_abladestelle(_gruppe([(930730000, 11, 700, True)]), "307M7")
    assert [(z["Norm-Nr"], z["Menge"]) for z in plan] == [(930730000, 7000)]
    assert not plan[0]["Menge_gerundet"]  # Aufrundung steckt in der abgetrennten KLT
    assert [(z["Norm-Nr"], z["Menge"], z["Menge_gerundet"]) for z in dhl] == [(930730000, 700, True)]


def test_angefangene_lage_ab_5_klt_bleibt_auf_der_palette(spez):
    spez[("X", 1)] = {"anzahl_pro_lage": 10, "anzahl_volle_palette": 30, "typ": 111444}
    plan, dhl = pe._plane_abladestelle(_gruppe([(1, 17, 100, False), (2, 20, 100, False)]), "X")
    assert {z["Norm-Nr"]: z["Menge"] for z in plan} == {1: 1700, 2: 2000}
    assert dhl == []
    assert all("Paletten Anzahl" not in z for z in plan)  # Formeln rechnen normal


def test_mix_palette_aus_kleinen_artikeln_wird_sichtbar(spez):
    # Beispiel 307K2: 3 + 2 + 1 KLT -> eine Mix-Palette 1 x 111444
    spez[("307K2", 101182800)] = {"anzahl_pro_lage": 10, "anzahl_volle_palette": 10, "typ": 111444}
    gruppe = _gruppe([(101182800, 3, 650, True), (100327000, 2, 2100, False), (100326400, 1, 800, False)])
    plan, dhl = pe._plane_abladestelle(gruppe, "307K2")
    assert dhl == []
    zeilen = {z["Norm-Nr"]: z for z in plan}
    traeger = zeilen[101182800]
    assert traeger["Paletten Typ"] == "111444" and traeger["Paletten Anzahl"] == 1
    assert traeger["Hinweis"].startswith("Mix-Palette (003147) 3 + 2 + 1 = 6 KLT")
    for n in (100327000, 100326400):
        assert "Paletten Anzahl" not in zeilen[n] and "Paletten Typ" not in zeilen[n]
        assert "Mix-Palette bei 101182800" in zeilen[n]["Hinweis"]
    assert zeilen[100327000]["Menge"] == 4200


def test_kleine_reste_ohne_partner_zu_dhl_ups(spez):
    plan, dhl = pe._plane_abladestelle(_gruppe([(1, 2, 100, False), (2, 2, 100, False)]), "X")
    assert plan == [] and {z["Norm-Nr"] for z in dhl} == {1, 2}


def test_rest_eines_grossen_artikels_geht_zu_dhl_nicht_auf_mix(spez):
    # 12 KLT (10/Lage): 10 auf eigener Palette, 2 -> DHL UPS. Die 3 + 2 KLT der
    # kleinen Artikel ergeben zusammen eine Mix-Palette.
    gruppe = _gruppe([(1, 12, 100, False), (2, 3, 100, False), (3, 2, 100, False)])
    plan, dhl = pe._plane_abladestelle(gruppe, "X")
    zeilen = {z["Norm-Nr"]: z for z in plan}
    assert zeilen[1]["Menge"] == 1000 and "Paletten Anzahl" not in zeilen[1]
    assert [(z["Norm-Nr"], z["Menge"]) for z in dhl] == [(1, 200)]
    assert zeilen[2]["Paletten Anzahl"] == 1 and zeilen[2]["Paletten Typ"] == "111444"
    assert "Paletten Anzahl" not in zeilen[3]


def test_mix_palette_in_datei_geschrieben(spez):
    positionen = _positionen([(A_ALT, "20A", "2026-11-05", 3), (A_NEU, "20A", "2026-11-05", 2)])
    inhalt, kennzahlen, _ = pe.erstelle_planungsdatei(
        positionen, _bestand({A_ALT: 3, A_NEU: 2}), None, PLANUNG, stichtag=STICHTAG
    )
    ws = openpyxl.load_workbook(io.BytesIO(inhalt))["Almanca"]
    r = _zeilen(ws)[A_ALT]
    assert ws.cell(row=r, column=14).value == "111444" and ws.cell(row=r, column=17).value == 1
    assert ws.cell(row=r, column=26).value.startswith("Mix-Palette 3 + 2 = 5 KLT")
    formel = ws.cell(row=_zeilen(ws)[A_NEU], column=14).value
    assert getattr(formel, "text", formel).startswith("=")  # Formel bleibt
    assert kennzahlen["mix_paletten"] == 1


# --- Vorziehen ---------------------------------------------------------------

def test_vorziehen_in_bestehende_planung(daten):
    positionen, bestand, zugang = daten
    # Bestehende Planung ohne A_ALT (z. B. erstellt, bevor die Ware da war)
    inhalt, _, _ = pe.erstelle_planungsdatei(positionen, _bestand({A_NEU: 20}), zugang, PLANUNG, stichtag=STICHTAG)
    wb_alt = openpyxl.load_workbook(io.BytesIO(inhalt))
    ws_alt = wb_alt["Almanca"]
    ws_alt.cell(row=_zeilen(ws_alt)[A_NEU], column=12, value="3000123456")  # manueller Eintrag
    puffer = io.BytesIO()
    wb_alt.save(puffer)
    bestehend = puffer.getvalue()

    kandidaten = pe.vorzieh_kandidaten(positionen, bestand, STICHTAG, bestehend)
    assert list(kandidaten["Norm-Nr"]) == [A_ALT]  # A_NEU kein Rueckstand, schon drin
    assert kandidaten.iloc[0]["Ziel"] == "Almanca"

    neu_bytes = pe.ergaenze_bestehende_planung(bestehend, kandidaten)
    ws = openpyxl.load_workbook(io.BytesIO(neu_bytes))["Almanca"]
    zeilen = _zeilen(ws)
    assert ws.cell(row=zeilen[A_NEU], column=12).value == "3000123456"  # unveraendert
    assert zeilen[A_ALT] == zeilen[A_NEU] + 2  # eine Leerzeile Abstand
    assert ws.cell(row=zeilen[A_ALT], column=6).font.color.rgb == pe.ROT
    assert ws.cell(row=zeilen[A_ALT], column=12).value.date() == pd.Timestamp("2026-10-20").date()
    assert pe.vorzieh_kandidaten(positionen, bestand, STICHTAG, neu_bytes).empty


def test_vorziehen_teilt_angefangene_lage_ab(daten, spez):
    _, _, zugang = daten
    positionen = _positionen([(A_ALT, "20A", "2026-10-20", 13)])  # 10 KLT/Lage -> 10 + 3
    inhalt, _, _ = pe.erstelle_planungsdatei(positionen, _bestand({}), zugang, PLANUNG, stichtag=STICHTAG)
    kandidaten = pe.vorzieh_kandidaten(positionen, _bestand({A_ALT: 13}), STICHTAG, inhalt)
    assert list(zip(kandidaten["Ziel"], kandidaten["Packeinheiten"])) == [("Almanca", 10), ("DHL UPS", 3)]
    wb = openpyxl.load_workbook(io.BytesIO(pe.ergaenze_bestehende_planung(inhalt, kandidaten)))
    r = _zeilen(wb["DHL UPS"])[A_ALT]
    assert wb["DHL UPS"].cell(row=r, column=9).fill.fgColor.rgb == pe.GRUEN_FUELLUNG.fgColor.rgb
    assert wb["DHL UPS"].cell(row=r, column=12).value.date() == pd.Timestamp("2026-10-20").date()
    assert wb["Almanca"].cell(row=_zeilen(wb["Almanca"])[A_ALT], column=9).value == 10


# --- Anfrage 04.11. (2): KLT-Art, Bestandsgrenze, DHL UPS gruen -------------

def test_mix_nur_bei_gleicher_klt_art(spez, monkeypatch):
    monkeypatch.setattr(pe, "_KLT_ART_STAMM", {("X", 1): "003147", ("X", 2): "004147", ("X", 3): "003147"})
    monkeypatch.setattr(pe, "_KLT_ART_SAP", {})
    gruppe = _gruppe([(1, 3, 100, False), (2, 3, 100, False), (3, 2, 100, False)])
    plan, dhl = pe._plane_abladestelle(gruppe, "X")
    assert {z["Norm-Nr"] for z in plan} == {1, 3}  # 3 + 2 KLT 003147 -> Mix
    assert [z["Norm-Nr"] for z in dhl] == [2]       # 004147 nicht dazu
    assert "(003147)" in {z["Norm-Nr"]: z for z in plan}[1]["Hinweis"]


def test_klt_art_aus_vorlage_wie_formel_r():
    assert pe._klt_art("15501", 100217000) == "003147"
    assert set(pe._KLT_ART_STAMM.values()) <= {"003147", "004147"}
    assert "004147" in set(pe._KLT_ART_STAMM.values())


def test_aufrunden_nie_ueber_bestand(spez):
    # Fuellmenge 1 im Test -> Rundung greift nicht; deshalb Fuellmenge direkt setzen
    gerundet = pd.DataFrame([
        {"Abladestelle": "A", "Norm-Nr": 7, "Ladedatum": pd.Timestamp("2026-10-01"), "Menge urspruenglich": 2700.0,
         "Fuellmenge": 2800.0, "Packeinheiten": 1, "Menge": 2800.0, "Menge_gerundet": True, "VW-Nr": ""},
        {"Abladestelle": "B", "Norm-Nr": 7, "Ladedatum": pd.Timestamp("2026-10-02"), "Menge urspruenglich": 2700.0,
         "Fuellmenge": 2800.0, "Packeinheiten": 1, "Menge": 2800.0, "Menge_gerundet": True, "VW-Nr": ""},
        {"Abladestelle": "C", "Norm-Nr": 7, "Ladedatum": pd.Timestamp("2026-10-03"), "Menge urspruenglich": 2600.0,
         "Fuellmenge": 2800.0, "Packeinheiten": 1, "Menge": 2800.0, "Menge_gerundet": True, "VW-Nr": ""},
    ])
    # 8.000 Stk ergaeben aufgerundet 3 KLT = 8.400, nutzbar sind aber nur 2 KLT (5.600)
    begrenzt, zusatz = pe._begrenze_auf_bestand(gerundet, {7: 5600})
    assert begrenzt["Menge"].sum() == 5600
    assert list(begrenzt["Abladestelle"]) == ["A", "B"]  # aeltestes Ladedatum zuerst
    assert list(zusatz["Abladestelle"]) == ["C"] and zusatz["Offene Menge"].iloc[0] == 2600


def test_dhl_ups_zeile_a_bis_t_gruen(daten):
    positionen = _positionen([(A_ALT, "20A", "2026-11-05", 3)])
    inhalt, _, _ = pe.erstelle_planungsdatei(positionen, _bestand({A_ALT: 3}), None, PLANUNG, stichtag=STICHTAG)
    ws = openpyxl.load_workbook(io.BytesIO(inhalt))["DHL UPS"]
    r = _zeilen(ws)[A_ALT]
    gruen = pe.GRUEN_FUELLUNG.fgColor.rgb
    assert all(ws.cell(row=r, column=c).fill.fgColor.rgb == gruen for c in range(1, 21))
    assert ws.cell(row=r, column=21).fill.fgColor.rgb != gruen


def test_artikel_diagnose_erklaert_gruende(daten):
    positionen, bestand, zugang = daten
    zu_spaet = pe.artikel_diagnose(positionen, bestand, zugang, "2026-10-25", A_NEU)
    assert any("nach dem Planungsdatum" in m for m in zu_spaet["meldungen"])
    ohne_bestand = pe.artikel_diagnose(positionen, bestand, zugang, PLANUNG, A_ERW)
    assert any("Kein nutzbarer Bestand" in m for m in ohne_bestand["meldungen"])
    assert any("NRI2026000000001" in m for m in ohne_bestand["meldungen"])
    geplant = pe.artikel_diagnose(positionen, bestand, zugang, PLANUNG, A_ALT)
    assert any(m.startswith("✅ Eingeplant") for m in geplant["meldungen"])
    assert pe.artikel_diagnose(positionen, bestand, zugang, PLANUNG, 123)["meldungen"][-1].startswith("❌ Kein offener Bedarf")


def test_checkboxen_in_spalte_w_bleiben_erhalten(daten):
    import re
    import zipfile
    positionen, bestand, zugang = daten
    inhalt, _, _ = pe.erstelle_planungsdatei(positionen, bestand, zugang, PLANUNG, stichtag=STICHTAG)
    z = zipfile.ZipFile(io.BytesIO(inhalt))
    assert pe.FPB_PFAD in z.namelist()
    assert pe.FPB_REL_TYP in z.read("xl/_rels/workbook.xml.rels").decode()
    assert pe.FPB_PFAD in z.read("[Content_Types].xml").decode()
    styles = z.read("xl/styles.xml").decode()
    xfs = re.findall(r"<xf\b[^>]*?/>|<xf\b[^>]*?>.*?</xf>", re.search(r"<cellXfs[^>]*>(.*?)</cellXfs>", styles, re.S).group(1), re.S)
    pfade = pe._blatt_pfade({n: z.read(n) for n in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels")})
    for blatt in pe.CHECKBOX_BLAETTER:
        xml = z.read(pfade[blatt]).decode()
        stile = re.findall(r'<c r="W(\d+)" s="(\d+)" t="b"', xml)
        assert len(stile) > 600
        assert all(pe.CHECKBOX_URI in xfs[int(s)] for zeile, s in stile if int(zeile) >= 5)
    # Vorziehen (laedt + speichert erneut) behaelt sie ebenfalls, ohne doppelt einzufuegen
    kandidaten = pe.vorzieh_kandidaten(positionen, bestand, STICHTAG, inhalt)
    neu = zipfile.ZipFile(io.BytesIO(pe.ergaenze_bestehende_planung(inhalt, kandidaten) if len(kandidaten) else inhalt))
    assert pe.CHECKBOX_URI in neu.read("xl/styles.xml").decode()
    assert neu.read("xl/_rels/workbook.xml.rels").decode().count(pe.FPB_REL_TYP) == 1


def test_zweite_checkbox_schon_ausgebucht_und_farben(daten):
    import re
    import zipfile
    positionen, bestand, zugang = daten
    inhalt, _, _ = pe.erstelle_planungsdatei(positionen, bestand, zugang, PLANUNG, stichtag=STICHTAG)
    wb = openpyxl.load_workbook(io.BytesIO(inhalt))
    for blatt in ("Almanca", "DHL UPS"):
        ws = wb[blatt]
        assert ws["AB4"].value == "Schon ausgebucht" and ws["AB5"].value is False
        regeln = sorted(((r.priority, r.formula[0], str(cf.sqref)) for cf in ws.conditional_formatting for r in cf.rules), key=lambda x: x[0])
        assert {(p, f) for p, f, _ in regeln[:4]} == {(1, pe._block_status("AB")), (2, pe._block_status("W"))}
        assert {b.split(":")[0] for _, _, b in regeln[:4]} == {"T5", "W5"}
    assert "$AB$5" in wb["Almanca"]["X2"].value
    z = zipfile.ZipFile(io.BytesIO(inhalt))
    styles = z.read("xl/styles.xml").decode()
    xfs = re.findall(r"<xf\b[^>]*?/>|<xf\b[^>]*?>.*?</xf>", re.search(r"<cellXfs[^>]*>(.*?)</cellXfs>", styles, re.S).group(1), re.S)
    xml = z.read(pe._blatt_pfade({n: z.read(n) for n in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels")})["Almanca"]).decode()
    ab = re.findall(r'<c r="AB(\d+)" s="(\d+)" t="b"', xml)
    assert len(ab) > 600 and all(pe.CHECKBOX_URI in xfs[int(s)] for _, s in ab)
    # erneutes Speichern (Vorziehen) fuegt nichts doppelt ein
    neu = openpyxl.load_workbook(io.BytesIO(pe.ergaenze_bestehende_planung(inhalt, pe.vorzieh_kandidaten(positionen, bestand, STICHTAG, inhalt))))
    assert sum(1 for cf in neu["Almanca"].conditional_formatting for r in cf.rules if r.formula == [pe._block_status("AB")]) == 2
