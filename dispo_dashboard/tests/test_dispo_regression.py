"""
Regressionstest: hält die Ergebnisse mit den Testdaten vom 06.10.2026 fest.
Schlägt er fehl, hat sich an der Rechenlogik etwas geändert.

    pytest dispo_dashboard/tests          (oder ohne pytest:)
    python -m dispo_dashboard.tests.test_dispo_regression
"""
from datetime import date
from pathlib import Path

from dispo_dashboard import loaders, logic

TESTDATEN = Path(__file__).resolve().parents[2] / "dispo_testdaten"
STICHTAG = date(2026, 10, 6)


def _rechne():
    dateien = {t: p for t, (p, _) in loaders.neueste_dateien(TESTDATEN).items()}
    bedarf = loaders.lade_bedarf(dateien["bedarf"])
    _, bestand = loaders.lade_bestand(dateien["bestand"])
    zugang = loaders.lade_zugang(dateien["zugang"])
    return dateien, bedarf, bestand, zugang, *logic.berechne(bedarf, bestand, zugang, STICHTAG)


def test_dateien_erkannt():
    dateien = _rechne()[0]
    assert set(dateien) == {"bedarf", "bestand", "zugang", "stockreport"}


def test_eingangsdaten():
    _, bedarf, bestand, zugang, *_ = _rechne()
    assert len(bedarf) == 12557
    assert int(bestand["F2"].sum()) == 33_984_887
    assert int(bestand["K2"].sum()) == 3_669_194
    assert int(zugang["Menge"].sum()) == 46_974_790


def test_status_je_einteilung():
    p = _rechne()[4]
    assert p["Status"].value_counts().to_dict() == {
        "Fehlmenge später": 9362, "Gedeckt": 2846, "Erledigt": 122, "Zugang zu spät": 111,
        "Engpass": 83, "Rückstand, Zugang kommt": 14, "Rückstand ungedeckt": 11, "Rückstand gedeckt": 8,
    }
    assert int(p["Offene Menge"].sum()) == 519_123_925


def test_ampel_je_artikel():
    a = _rechne()[5]
    assert a["Ampel"].value_counts().to_dict() == {"Grün": 122, "Rot": 30, "Gelb": 12}


def test_stockreport_nur_info():
    dateien = _rechne()[0]
    sr = loaders.lade_stockreport(dateien["stockreport"])
    assert len(sr) == 420
    assert loaders.datum_der_datei(dateien["stockreport"], STICHTAG) == date(2026, 9, 28)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK ", name)
