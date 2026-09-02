"""Tests fuer reklamation_lokal.py (lokale Reklamations-Erfassung per Drag & Drop)."""

import datetime
import os

from fpdf import FPDF

import reklamation_lokal as rl


def _baue_test_pdf_mit_beleg_box(beleg_nr="11785075", kto_nr="1023115", datum="27.08.2026"):
    """Baut eine minimale synthetische PDF mit dem gleichen Spalten-Layout
    wie der Duvenbeck-Kasten "Bei Zahlung bitte angeben" (Label-Zeile +
    Werte-Zeile, je Spalte gleiche linke Kante) - ohne echte Rechnungsdaten."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    pdf.set_xy(50, 50)
    pdf.cell(40, 7, "Beleg-Nr.")
    pdf.set_xy(100, 50)
    pdf.cell(40, 7, "Kto-Nr.")
    pdf.set_xy(150, 50)
    pdf.cell(40, 7, "Datum")

    pdf.set_xy(50, 59)
    pdf.cell(40, 9, beleg_nr)
    pdf.set_xy(100, 59)
    pdf.cell(40, 9, kto_nr)
    pdf.set_xy(150, 59)
    pdf.cell(40, 9, datum)

    return bytes(pdf.output())


def _baue_test_pdf_ohne_beleg_box():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.set_xy(20, 20)
    pdf.cell(100, 7, "Ein ganz anderes Dokument ohne die erwartete Box.")
    return bytes(pdf.output())


def _baue_test_pdf_mit_text(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.set_xy(20, 20)
    pdf.multi_cell(150, 7, text)
    return bytes(pdf.output())


def test_extrahiere_beleg_und_datum_erkennt_layout():
    pdf_bytes = _baue_test_pdf_mit_beleg_box(
        beleg_nr="99887766", kto_nr="12345", datum="01.02.2026"
    )
    beleg_nr, datum = rl.extrahiere_beleg_und_datum(pdf_bytes)
    assert beleg_nr == "99887766"
    assert datum == "01.02.2026"


def test_extrahiere_beleg_und_datum_ohne_passendes_layout_gibt_none():
    pdf_bytes = _baue_test_pdf_ohne_beleg_box()
    assert rl.extrahiere_beleg_und_datum(pdf_bytes) == (None, None)


def test_extrahiere_beleg_und_datum_bei_kaputter_pdf_gibt_none():
    assert rl.extrahiere_beleg_und_datum(b"das ist keine PDF-Datei") == (None, None)


def test_sicherer_pdf_dateiname_mit_belegnr():
    assert rl.sicherer_pdf_dateiname("11785075", "original.pdf") == "11785075.pdf"


def test_sicherer_pdf_dateiname_fallback_ohne_belegnr():
    assert rl.sicherer_pdf_dateiname(None, "Meine Rechnung.pdf") == "Meine Rechnung.pdf"


def test_sicherer_pdf_dateiname_saniert_unsichere_zeichen():
    assert rl.sicherer_pdf_dateiname("117/850 75", "x.pdf") == "117_850 75.pdf"


def test_extrahiere_abholtag_erkennt_vom_muster():
    pdf_bytes = _baue_test_pdf_mit_text("Reise: H FVX 024 vom 10.08.2026")
    assert rl.extrahiere_abholtag(pdf_bytes) == "10.08.2026"


def test_extrahiere_abholtag_erkennt_abholtag_muster_mit_kurzjahr():
    pdf_bytes = _baue_test_pdf_mit_text("Solldaten ( Abholtag 10.08.26 ):")
    assert rl.extrahiere_abholtag(pdf_bytes) == "10.08.2026"


def test_extrahiere_abholtag_ohne_muster_gibt_none():
    pdf_bytes = _baue_test_pdf_mit_text("Kein passendes Datum hier drin.")
    assert rl.extrahiere_abholtag(pdf_bytes) is None


def test_extrahiere_betrag_erkennt_endbetrag():
    pdf_bytes = _baue_test_pdf_mit_text("Summe 394,00 EUR\nEndbetrag 468,86 EUR")
    assert rl.extrahiere_betrag(pdf_bytes) == "468,86 EUR"


def test_extrahiere_betrag_ohne_endbetrag_gibt_none():
    pdf_bytes = _baue_test_pdf_mit_text("Kein Endbetrag auf dieser Seite.")
    assert rl.extrahiere_betrag(pdf_bytes) is None


def test_extrahiere_firma_erkennt_empfaenger():
    pdf_bytes = _baue_test_pdf_mit_text(
        "Absender : Norm Fasteners GmbH . D-47807 Krefeld\n"
        "Empfänger : Skoda Auto a.s. . CZ-293 60 Mlada Boleslav"
    )
    assert rl.extrahiere_firma(pdf_bytes) == "Skoda Auto a.s."


def test_extrahiere_firma_ohne_muster_gibt_none():
    pdf_bytes = _baue_test_pdf_mit_text("Kein Empfaenger-Feld hier.")
    assert rl.extrahiere_firma(pdf_bytes) is None


def test_extrahiere_referenznummern_erkennt_liste():
    pdf_bytes = _baue_test_pdf_mit_text(
        "irgendwas SLB\nNummer:\n00330537;00330579;00330535"
    )
    assert rl.extrahiere_referenznummern(pdf_bytes) == [
        "00330537",
        "00330579",
        "00330535",
    ]


def test_extrahiere_referenznummern_ohne_muster_gibt_leere_liste():
    pdf_bytes = _baue_test_pdf_mit_text("Keine Nummer hier.")
    assert rl.extrahiere_referenznummern(pdf_bytes) == []


def test_zugewiesen_und_ergebnis_optionen_enthalten_erwartete_werte():
    assert rl.ZUGEWIESEN_OPTIONEN == [
        "",
        "Murat Kurt",
        "Okan Kocak",
        "Alperen Konar",
        "Levin Akarcay",
    ]
    assert rl.ERGEBNIS_OPTIONEN == ["", "Berechtigt", "Unberechtigt"]


def test_archiv_monatsordner_ersetzt_jahr_platzhalter():
    vorlage = r"C:\Firma\Archiv - {jahr}"
    ergebnis = rl.archiv_monatsordner(vorlage, "10.08.2026")
    assert ergebnis == os.path.join(r"C:\Firma\Archiv - 2026", "08")


def test_archiv_monatsordner_ohne_platzhalter_bleibt_unveraendert():
    vorlage = r"C:\Firma\Archiv"
    ergebnis = rl.archiv_monatsordner(vorlage, "10.08.2026")
    assert ergebnis == os.path.join(r"C:\Firma\Archiv", "08")


def test_erstelle_fallordner_findet_dateien_trotz_abweichender_trennzeichen(tmp_path):
    archiv = tmp_path / "Archiv"
    monatsordner = archiv / "08"
    monatsordner.mkdir(parents=True)
    (monatsordner / "20260810_Planung_VW_Planung.xlsx").write_text("planung")
    (monatsordner / "20260810 Planung VW_Ladeliste.xlsx").write_text("ladeliste")
    # Avisierung bewusst nicht angelegt, um die Fehlend-Meldung zu testen

    reklamationen_basis = tmp_path / "Reklamationen"
    reklamationen_basis.mkdir()
    rechnung = tmp_path / "11785075.pdf"
    rechnung.write_bytes(b"%PDF-1.4 dummy")

    fallordner, fehlend = rl.erstelle_fallordner(
        str(archiv), str(reklamationen_basis), "11785075", "10.08.2026", str(rechnung)
    )

    assert fallordner == str(reklamationen_basis / "Fall-11785075")
    assert fehlend == ["Avisierung"]
    erstellte_dateien = set(os.listdir(fallordner))
    assert erstellte_dateien == {
        "11785075.pdf",
        "20260810_Planung_VW_Planung.xlsx",
        "20260810 Planung VW_Ladeliste.xlsx",
    }


def test_erstelle_fallordner_ohne_monatsordner_meldet_alles_fehlend(tmp_path):
    reklamationen_basis = tmp_path / "Reklamationen"
    reklamationen_basis.mkdir()
    rechnung = tmp_path / "x.pdf"
    rechnung.write_bytes(b"%PDF-1.4 dummy")

    fallordner, fehlend = rl.erstelle_fallordner(
        str(tmp_path / "Archiv_gibt_es_nicht"),
        str(reklamationen_basis),
        "999",
        "01.01.2026",
        str(rechnung),
    )

    assert sorted(fehlend) == ["Avisierung", "Ladeliste", "Planung"]
    assert os.path.exists(os.path.join(fallordner, "x.pdf"))


def test_gespeicherter_archivordner_roundtrip(tmp_path, monkeypatch):
    config_datei = str(tmp_path / ".reklamationen_archivordner.txt")
    monkeypatch.setattr(rl, "ARCHIV_CONFIG_DATEI", config_datei)

    assert rl.lade_gespeicherten_archivordner() == rl.STANDARD_ARCHIV_BASISORDNER

    rl.speichere_archivordner(r"D:\Anderes\Archiv")
    assert rl.lade_gespeicherten_archivordner() == r"D:\Anderes\Archiv"


def test_guess_eingangsdatum_erkennt_datum_im_dateinamen():
    assert rl.guess_eingangsdatum("Ausfallfracht_20260305.pdf") == "05.03.2026"


def test_guess_eingangsdatum_ohne_muster_faellt_auf_heute_zurueck():
    heute = datetime.date.today().strftime("%d.%m.%Y")
    assert rl.guess_eingangsdatum("irgendeine_datei.pdf") == heute


def test_guess_absender_betreff_rechnung():
    result = rl.guess_absender_betreff("Ausfallfracht_20260305.pdf")
    assert result == {
        "Absender": rl.ABSENDER_DUVENBECK,
        "Betreff": rl.BETREFF_AUSFALLFRACHT,
    }


def test_guess_absender_betreff_storno_case_insensitive():
    result = rl.guess_absender_betreff("STORNO_Ausfallfracht_20260313.pdf")
    assert result == {
        "Absender": rl.ABSENDER_DUVENBECK,
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
            "Abholtag": "01.03.2026",
            "Firma": "Skoda Auto a.s.",
            "Absender": "Duvenbeck",
            "Betreff": "Ausfallfracht Rechnung",
            "Dateiname_PDF": "Ausfallfracht_20260305.pdf",
            "OneDrive_Pfad": r"C:\Basis\Rechnungen_PDF\Ausfallfracht_20260305.pdf",
            "Betrag": "394,00 EUR",
            "Zugewiesen": "Murat Kurt",
            "Status": "Offen",
            "Prüfdatum": "",
            "Ergebnis": "",
            "Bemerkung": "",
            "Referenznummern": "00330537;00330579",
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
