"""Tests fuer reklamation_lokal.py (lokale Reklamations-Erfassung per Drag & Drop)."""

import datetime
import os

import reklamation_lokal as rl


def test_guess_eingangsdatum_erkennt_datum_im_dateinamen():
    assert rl.guess_eingangsdatum("Ausfallfracht_20260305.pdf") == "05.03.2026"


def test_guess_eingangsdatum_ohne_muster_faellt_auf_heute_zurueck():
    heute = datetime.date.today().strftime("%d.%m.%Y")
    assert rl.guess_eingangsdatum("irgendeine_datei.pdf") == heute


def test_guess_absender_betreff_rechnung():
    result = rl.guess_absender_betreff("Ausfallfracht_20260305.pdf")
    assert result == {
        "Absender": rl.ABSENDER_AUSFALLFRACHT,
        "Betreff": rl.BETREFF_AUSFALLFRACHT,
    }


def test_guess_absender_betreff_storno_case_insensitive():
    result = rl.guess_absender_betreff("STORNO_Ausfallfracht_20260313.pdf")
    assert result == {
        "Absender": rl.ABSENDER_STORNO,
        "Betreff": rl.BETREFF_STORNO,
    }


def test_excel_pfad_und_pdf_ordner(tmp_path):
    basis = str(tmp_path)
    assert rl.excel_pfad(basis) == os.path.join(basis, "VW_Reklamationen.xlsx")
    assert rl.pdf_ordner(basis) == os.path.join(basis, "Rechnungen_PDF")


def test_speichere_pdf_schreibt_datei_und_erstellt_ordner(tmp_path):
    basis = str(tmp_path / "Basis")
    pfad = rl.speichere_pdf(basis, "test.pdf", b"%PDF-1.4 dummy")

    assert os.path.exists(pfad)
    with open(pfad, "rb") as f:
        assert f.read() == b"%PDF-1.4 dummy"
    assert pfad == os.path.join(rl.pdf_ordner(basis), "test.pdf")


def test_speichere_pdf_ueberschreibt_nicht_bei_namenskollision(tmp_path):
    basis = str(tmp_path)
    pfad1 = rl.speichere_pdf(basis, "gleich.pdf", b"erste-datei")
    pfad2 = rl.speichere_pdf(basis, "gleich.pdf", b"zweite-datei")

    assert pfad1 != pfad2
    with open(pfad1, "rb") as f:
        assert f.read() == b"erste-datei"
    with open(pfad2, "rb") as f:
        assert f.read() == b"zweite-datei"


def test_lade_excel_ohne_datei_gibt_leere_liste(tmp_path):
    assert rl.lade_excel(str(tmp_path / "fehlt.xlsx")) == []


def test_speichere_und_lade_excel_roundtrip(tmp_path):
    pfad = str(tmp_path / "test.xlsx")
    rows = [
        {
            "Eingangsdatum": "05.03.2026",
            "Absender": "noreply@duvenbeck.de",
            "Betreff": "Rechnung Ausfallfracht zu Frachtbrief",
            "Dateiname_PDF": "Ausfallfracht_20260305.pdf",
            "OneDrive_Pfad": r"C:\Basis\Rechnungen_PDF\Ausfallfracht_20260305.pdf",
            "Status": "Offen",
            "Prüfdatum": "",
            "Ergebnis": "",
            "Bemerkung": "",
        }
    ]
    rl.speichere_excel(pfad, rows)

    geladen = rl.lade_excel(pfad)
    assert geladen == rows


def test_speichere_excel_erstellt_ordner_falls_noetig(tmp_path):
    pfad = str(tmp_path / "unterordner" / "test.xlsx")
    rl.speichere_excel(pfad, [])
    assert os.path.exists(pfad)


def test_gespeicherter_basisordner_roundtrip(tmp_path, monkeypatch):
    config_datei = str(tmp_path / ".reklamationen_basisordner.txt")
    monkeypatch.setattr(rl, "PFAD_CONFIG_DATEI", config_datei)

    assert rl.lade_gespeicherten_basisordner() == rl.STANDARD_BASISORDNER

    rl.speichere_basisordner(r"D:\Anderer\Ordner")
    assert rl.lade_gespeicherten_basisordner() == r"D:\Anderer\Ordner"
