import datetime
import io
import sys
from pathlib import Path

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ladeliste_logic as ll


# ---------------------------------------------------------------------------
# PAL-Regex-Logik
# ---------------------------------------------------------------------------

def test_pal_example_1_drei_ladungstraeger():
    text = "10*VWPAL / 19*111444 / 600*003147"
    assert ll.process_pal(text) == "10*VWPAL / 19*111444"


def test_pal_example_2_nur_111444():
    text = "3*111444 / 3*001006 / 70*003147"
    assert ll.process_pal(text) == "3*111444"


def test_pal_example_3_kein_treffer():
    text = "Dein"
    assert ll.process_pal(text) == ""


def test_pal_none_wert():
    assert ll.process_pal(None) == ""


def test_pal_leerer_text():
    assert ll.process_pal("") == ""


def test_pal_reihenfolge_111444_zuerst():
    text = "7*111444 / 4*VWPAL"
    assert ll.process_pal(text) == "7*111444 / 4*VWPAL"


def test_pal_nur_vwpal():
    text = "5*VWPAL"
    assert ll.process_pal(text) == "5*VWPAL"


def test_pal_case_insensitive():
    text = "8*vwpal / 2*111444"
    assert ll.process_pal(text) == "8*VWPAL / 2*111444"


def test_pal_beliebige_leerzeichen_um_stern_und_slash():
    text = "10 *  VWPAL   /   19*  111444"
    assert ll.process_pal(text) == "10*VWPAL / 19*111444"


def test_pal_ohne_leerzeichen_um_stern():
    text = "10*VWPAL/19*111444"
    assert ll.process_pal(text) == "10*VWPAL / 19*111444"


def test_pal_mehrfaches_vorkommen_wird_summiert():
    text = "5*VWPAL / 2*111444 / 3*VWPAL"
    assert ll.process_pal(text) == "8*VWPAL / 2*111444"


def test_pal_ignoriert_aehnliche_aber_andere_ladungstraeger():
    text = "100*111445 / 3*VWPALX / 4*111444"
    assert ll.process_pal(text) == "4*111444"


# ---------------------------------------------------------------------------
# Zusammenfuehren mehrerer Quelldateien
# ---------------------------------------------------------------------------

def _make_source_workbook_bytes(header, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = ll.SOURCE_SHEET_NAME
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


HEADER = [f"col{i}" for i in range(15)]


def _row(lkw="LKW1", pal="1*VWPAL", brutto=100, name="Empfaenger"):
    row = [None] * 15
    row[ll.COL_ABHOLTAG] = datetime.date(2026, 1, 1)
    row[ll.COL_EMPF_NAME] = name
    row[ll.COL_EMPF_ORT] = "Ort"
    row[ll.COL_ABLADESTELLE] = "Stelle"
    row[ll.COL_LKW_VL] = lkw
    row[ll.COL_PAL_QUELLE] = pal
    row[ll.COL_BRUTTO] = brutto
    return row


def test_merge_haelt_reihenfolge_ueber_mehrere_dateien():
    rows1 = [_row(name="A1"), _row(name="A2"), _row(name="A3")]
    rows2 = [_row(name="B1"), _row(name="B2")]
    file1 = _make_source_workbook_bytes(HEADER, rows1)
    file2 = _make_source_workbook_bytes(HEADER, rows2)

    header, merged = ll.merge_source_files([file1, file2])

    assert header == HEADER
    names = [row[ll.COL_EMPF_NAME] for row in merged]
    assert names == ["A1", "A2", "A3", "B1", "B2"]


def test_merge_uebernimmt_kopfzeile_nur_einmal():
    file1 = _make_source_workbook_bytes(HEADER, [_row(name="A1")])
    file2 = _make_source_workbook_bytes([f"anders{i}" for i in range(15)], [_row(name="B1")])

    header, merged = ll.merge_source_files([file1, file2])

    assert header == HEADER
    assert len(merged) == 2


def test_merge_ohne_sortierung_oder_dedupe():
    rows1 = [_row(name="Gleich"), _row(name="Gleich")]
    file1 = _make_source_workbook_bytes(HEADER, rows1)

    header, merged = ll.merge_source_files([file1])

    assert len(merged) == 2


def test_merge_ohne_dateien_wirft_fehler():
    try:
        ll.merge_source_files([])
        assert False, "Erwartete ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# LKW-Gruppierung
# ---------------------------------------------------------------------------

def test_build_truck_groups_ignoriert_leere_lkw_spalte():
    rows = [_row(lkw="LKW1"), _row(lkw=None), _row(lkw="   "), _row(lkw="LKW2")]
    groups = ll.build_truck_groups(rows)
    assert list(groups.keys()) == ["LKW1", "LKW2"]
    assert len(groups["LKW1"]) == 1
    assert len(groups["LKW2"]) == 1


def test_build_truck_groups_erhaelt_reihenfolge_je_gruppe():
    rows = [
        _row(lkw="LKW1", name="Erste"),
        _row(lkw="LKW2", name="Zweite"),
        _row(lkw="LKW1", name="Dritte"),
    ]
    groups = ll.build_truck_groups(rows)
    names = [e.empf_name for e in groups["LKW1"]]
    assert names == ["Erste", "Dritte"]


# ---------------------------------------------------------------------------
# End-to-End: generierte Arbeitsmappe besteht alle Validierungen
# ---------------------------------------------------------------------------

def test_generate_workbook_end_to_end_validiert_fehlerfrei():
    rows = [
        _row(lkw="LKW1", pal="10*VWPAL / 19*111444 / 600*003147", brutto=9350.3, name="A"),
        _row(lkw="LKW1", pal="3*111444 / 3*001006 / 70*003147", brutto=100.5, name="B"),
        _row(lkw="LKW2", pal="Dein", brutto=50, name="C"),
    ]
    file1 = _make_source_workbook_bytes(HEADER, rows)

    result = ll.generate_workbook([file1])

    assert result.is_valid, [v.message for v in result.validation if not v.passed]
    assert {s.sheet_name for s in result.summaries} == {"LKW LKW1", "LKW LKW2"}

    lkw1 = next(s for s in result.summaries if s.sheet_name == "LKW LKW1")
    assert lkw1.position_count == 2
    assert lkw1.total_111444 == 22
    assert lkw1.total_vwpal == 10
    assert abs(lkw1.gesamtgewicht - 9450.8) < 1e-9
