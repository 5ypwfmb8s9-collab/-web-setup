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


def test_erwartet_bereich_gelb_unten_und_nicht_in_summe(daten):
    wb, kennzahlen, _ = _erstelle(daten)
    ws = wb["Almanca"]
    zeilen = _zeilen(ws)
    erw = zeilen[A_ERW]
    assert erw > max(zeilen[A_ALT], zeilen[A_NEU]) + 1  # eigener Bereich mit Leerzeile
    assert A_NIX not in zeilen  # NRI kommt erst nach dem Planungsdatum
    assert ws.cell(row=erw, column=9).value == 25
    assert ws.cell(row=erw, column=26).value == pe.ERWARTET_MARKER
    assert "NRI2026000000001" in ws.cell(row=erw, column=13).value
    assert ws.cell(row=erw, column=12).value.date() == pd.Timestamp("2026-10-28").date()
    for spalte in range(1, 21):
        assert ws.cell(row=erw, column=spalte).fill.fgColor.rgb == "FFFFFF00"
    assert ws.cell(row=erw, column=21).fill.fgColor.rgb != "FFFFFF00"
    assert ws["E2"].value == pe.SUMME_PALETTEN and "Erwartet" in ws["E2"].value
    assert ws["H2"].value == pe.SUMME_GEWICHT
    assert kennzahlen["erwartet_zeilen"] == 1


def test_erwartete_menge_wird_nach_dringlichkeit_verteilt():
    rueck = _positionen([(A_NIX, "05C", "2026-10-15", 12), (A_NIX, "01D", "2026-10-30", 8)])
    zugang = _zugang([(A_NIX, "NRI1", "2026-11-04", 15)])
    zeilen = pe._erwartete_zeilen(rueck, zugang, PLANUNG)
    mengen = {z["Abladestelle"]: z["Menge"] for z in zeilen}
    assert mengen == {"05C": 12, "01D": 3}


def test_vorziehen_in_bestehende_planung(daten):
    positionen, bestand, zugang = daten
    # Bestehende Planung ohne A_ALT (z. B. erstellt, bevor die Ware da war)
    inhalt, _, _ = pe.erstelle_planungsdatei(positionen, _bestand({A_NEU: 20}), zugang, PLANUNG, stichtag=STICHTAG)
    ws_alt = openpyxl.load_workbook(io.BytesIO(inhalt))["Almanca"]
    erw_alt = _zeilen(ws_alt)[A_ERW]
    ws_alt.cell(row=_zeilen(ws_alt)[A_NEU], column=12, value="3000123456")  # manueller Eintrag

    puffer = io.BytesIO()
    ws_alt.parent.save(puffer)
    bestehend = puffer.getvalue()

    kandidaten = pe.vorzieh_kandidaten(positionen, bestand, STICHTAG, bestehend)
    assert list(kandidaten["Norm-Nr"]) == [A_ALT]  # A_NEU kein Rueckstand, schon drin
    assert kandidaten.iloc[0]["Ziel"] == "Almanca"

    neu = openpyxl.load_workbook(io.BytesIO(pe.ergaenze_bestehende_planung(bestehend, kandidaten)))
    ws = neu["Almanca"]
    zeilen = _zeilen(ws)
    assert ws.cell(row=zeilen[A_NEU], column=12).value == "3000123456"  # unveraendert
    assert zeilen[A_ALT] > zeilen[A_NEU]
    assert ws.cell(row=zeilen[A_ALT], column=6).font.color.rgb == pe.ROT
    # gelber Bereich nach unten gerueckt, inkl. Formatierung und Kennzeichnung
    assert zeilen[A_ERW] > zeilen[A_ALT] + 1
    assert zeilen[A_ERW] > erw_alt
    assert ws.cell(row=zeilen[A_ERW], column=26).value == pe.ERWARTET_MARKER
    assert ws.cell(row=zeilen[A_ERW], column=1).fill.fgColor.rgb == "FFFFFF00"
    assert ws.cell(row=erw_alt, column=1).fill.fgColor.rgb != "FFFFFF00" or erw_alt == zeilen[A_ERW]
    # erneut angeboten wird nichts mehr
    assert pe.vorzieh_kandidaten(positionen, bestand, STICHTAG, pe.ergaenze_bestehende_planung(bestehend, kandidaten)).empty


def test_vorziehen_kleine_menge_nach_dhl_ups(daten):
    positionen, _, zugang = daten
    positionen = _positionen([(A_ALT, "20A", "2026-10-20", 3)])
    bestand = _bestand({A_ALT: 3})
    inhalt, _, _ = pe.erstelle_planungsdatei(positionen, _bestand({}), zugang, PLANUNG, stichtag=STICHTAG)
    kandidaten = pe.vorzieh_kandidaten(positionen, bestand, STICHTAG, inhalt)
    assert list(kandidaten["Ziel"]) == ["DHL UPS"]
    ws = openpyxl.load_workbook(io.BytesIO(pe.ergaenze_bestehende_planung(inhalt, kandidaten)))["DHL UPS"]
    r = _zeilen(ws)[A_ALT]
    assert ws.cell(row=r, column=9).fill.fgColor.rgb == pe.GRUEN_FUELLUNG.fgColor.rgb
    assert ws.cell(row=r, column=12).value.date() == pd.Timestamp("2026-10-20").date()


def test_erwartet_info_nennt_nur_genutzte_nri():
    rueck = _positionen([(A_NIX, "05C", "2026-10-15", 12), (A_NIX, "01D", "2026-10-30", 8)])
    zugang = _zugang([(A_NIX, "NRI1", "2026-11-04", 12), (A_NIX, "NRI2", "2026-11-05", 30)])
    zeilen = {z["Abladestelle"]: z for z in pe._erwartete_zeilen(rueck, zugang, PLANUNG)}
    assert "NRI1" in zeilen["05C"]["Zugang Info"] and "NRI2" not in zeilen["05C"]["Zugang Info"]
    assert zeilen["01D"]["Zugang Info"].startswith("NRI2")
    assert zeilen["01D"]["Menge"] == 8
