"""Coach-Kontext, Muster, Sicherheit, Import/Export."""

import io
import zipfile
from datetime import date, timedelta

from core import insights, safety
from db import repo
from services import coach_context, exporter, importer


# ---------------------------------------------------------------- Muster
def _meals_with_pattern():
    start = date(2026, 8, 1)
    meals = {}
    for i in range(20):
        d = start + timedelta(days=i)
        low = i % 2 == 0
        meals[d] = {"fruehstueck": 350, "mittag": 250 if low else 650, "abend": 900 if low else 600, "snack": 150}
    return meals


def test_lunch_vs_evening_detected():
    ins = insights.lunch_vs_evening(_meals_with_pattern())
    assert ins is not None and "300" in ins.text
    assert "kcal" not in ins.text_plain


def test_no_insight_without_enough_data():
    assert insights.lunch_vs_evening({date(2026, 1, 1): {"mittag": 100, "abend": 900}}) is None


def test_all_insights_runs_on_empty():
    assert insights.all_insights({}, {}, {}, date(2026, 9, 1)) == []


# ---------------------------------------------------------------- Sicherheit
def test_warning_signs():
    assert safety.warning_signs_in_text("Ich habe nach dem Essen erbrochen")
    assert safety.warning_signs_in_text("hatte wieder einen Essanfall")
    assert safety.warning_signs_in_text("Ich schäme mich so für das Essen")
    assert not safety.warning_signs_in_text("Was kann ich heute Abend kochen?")


def test_low_intake_hint():
    days = {date(2026, 9, i): 600 for i in range(1, 4)}
    assert safety.low_intake_hint(days)
    assert safety.low_intake_hint({date(2026, 9, 1): 600}) is None


def test_rapid_loss_hint():
    start = date(2026, 8, 1)
    fast = [(start + timedelta(days=i), 90 - 0.2 * i) for i in range(30)]  # 1,4 kg/Woche bei 90 kg
    assert safety.rapid_loss_hint(fast)
    slow = [(start + timedelta(days=i), 90 - 0.05 * i) for i in range(30)]
    assert safety.rapid_loss_hint(slow) is None


# ---------------------------------------------------------------- Coach-Kontext
def test_coach_summary_is_privacy_preserving(user_id):
    repo.update_profile(user_id, name="Geheimname")
    today = date(2026, 9, 24)
    for i in range(1, 15):
        repo.add_entries(user_id, today - timedelta(days=i), "mittag", [{"name": "Spezialsalat", "kcal": 600, "protein": 30}], "freitext")
    repo.upsert_weight(user_id, today - timedelta(days=10), 80)
    repo.upsert_weight(user_id, today, 79)
    summary, _ = coach_context.gather(user_id, repo.get_profile(user_id), today)
    assert "Geheimname" not in summary and "test@kano.de" not in summary
    assert "Spezialsalat" not in summary  # keine Einzeleinträge
    assert "30–39 Jahre" in summary and "Tagesziel" in summary


# ---------------------------------------------------------------- Import
def test_import_german_semicolon_csv():
    data = "Datum;Gewicht (kg);Schritte\n01.09.2026;80,4;8.123\n02.09.2026;80,1;10.050\n".encode()
    res = importer.parse("waage.csv", data)
    assert res.weights == [(date(2026, 9, 1), 80.4), (date(2026, 9, 2), 80.1)]
    assert res.activities[1]["steps"] == 10050


def test_import_garmin_style_lbs():
    data = b'Date,Weight\n"2026-09-01","176.4 lbs"\n"2026-09-03","175.0 lbs"\n'
    res = importer.parse("garmin.csv", data)
    assert res.weights[0] == (date(2026, 9, 1), 80.0)
    assert any("Pfund" in w for w in res.warnings)


def test_import_apple_health_xml():
    xml = b"""<?xml version="1.0"?><HealthData>
    <Record type="HKQuantityTypeIdentifierBodyMass" unit="kg" value="81.2" startDate="2026-09-01 07:10:00 +0200"/>
    <Record type="HKQuantityTypeIdentifierStepCount" unit="count" value="4000" startDate="2026-09-01 10:00:00 +0200"/>
    <Record type="HKQuantityTypeIdentifierStepCount" unit="count" value="3500" startDate="2026-09-01 18:00:00 +0200"/>
    </HealthData>"""
    res = importer.parse("export.xml", xml)
    assert res.weights == [(date(2026, 9, 1), 81.2)]
    assert res.activities[0]["steps"] == 7500


def test_import_garbage_gives_warning():
    res = importer.parse("x.csv", b"foo,bar\n1,2\n")
    assert res.warnings and not res.weights


# ---------------------------------------------------------------- Export
def test_csv_zip_contains_tables(user_id):
    repo.upsert_weight(user_id, date(2026, 9, 1), 80.5)
    data = exporter.csv_zip(user_id)
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert {"weights.csv", "food_log.csv", "profil.csv", "LIESMICH.txt"} <= set(zf.namelist())
    assert "80,50" in zf.read("weights.csv").decode("utf-8-sig")
    assert "password" not in zf.read("konto.csv").decode("utf-8-sig")


def test_pdf_report(user_id):
    today = date(2026, 9, 24)
    for i in range(10):
        repo.upsert_weight(user_id, today - timedelta(days=i), 80 - i * 0.1)
        repo.add_entries(user_id, today - timedelta(days=i), "abend", [{"name": "Käsespätzle – groß", "kcal": 800}], "freitext")
    pdf = exporter.pdf_report(user_id, repo.get_profile(user_id), today - timedelta(days=13), today)
    assert pdf[:4] == b"%PDF" and len(pdf) > 2000
