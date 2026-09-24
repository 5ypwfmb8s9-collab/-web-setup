import pytest

from core import nutrition as n


def test_mifflin_known_values():
    # Mann, 80 kg, 180 cm, 30 J: 10*80 + 6.25*180 - 5*30 + 5 = 1780
    assert n.bmr_mifflin("m", 80, 180, 30) == pytest.approx(1780)
    # Frau, 65 kg, 165 cm, 40 J: 650 + 1031.25 - 200 - 161 = 1320.25
    assert n.bmr_mifflin("w", 65, 165, 40) == pytest.approx(1320.25)
    # Divers liegt genau dazwischen
    assert n.bmr_mifflin("d", 65, 165, 40) == pytest.approx((1320.25 + 1486.25) / 2)


def test_target_respects_floor():
    r = n.safe_target(1500, 55, "w", "abnehmen", 0.75, height_cm=165, age=30)
    assert r.target_kcal >= n.MIN_KCAL["w"]
    assert r.capped


def test_deficit_limited_to_one_percent_bodyweight():
    # 60 kg → max 0,6 kg/Woche ≈ 660 kcal/Tag; gewünscht 0,75 kg ≈ 825 kcal
    r = n.safe_target(2600, 60, "w", "abnehmen", 0.75, height_cm=170, age=30)
    assert r.deficit <= 60 * 0.01 * 7700 / 7 + 10
    assert r.capped


def test_deficit_limited_to_quarter_of_tdee():
    r = n.safe_target(2000, 150, "m", "abnehmen", 0.75, height_cm=180, age=30)
    assert r.deficit <= 2000 * 0.25 + 10


def test_no_deficit_when_underweight_or_minor():
    r = n.safe_target(2000, 50, "w", "abnehmen", 0.5, height_cm=170, age=30)  # BMI 17,3
    assert r.deficit == 0
    r = n.safe_target(2200, 70, "m", "abnehmen", 0.5, height_cm=175, age=16)
    assert r.deficit == 0


def test_maintain_and_gain():
    assert n.safe_target(2400, 80, "m", "halten", 0.5).target_kcal == 2400
    assert n.safe_target(2400, 80, "m", "aufbauen", 0.5).target_kcal == 2650


def test_macros_add_up():
    m = n.macro_targets(2000, 80, "ausgewogen")
    kcal = m.protein_g * 4 + m.carbs_g * 4 + m.fat_g * 9
    assert kcal == pytest.approx(2000, abs=25)
    low = n.macro_targets(2000, 80, "low_carb")
    assert low.carbs_g * 4 <= 2000 * 0.25 + 4
    hp = n.macro_targets(2000, 80, "high_protein")
    assert hp.protein_g > m.protein_g


def test_goal_weight_issues():
    assert n.goal_weight_issues("abnehmen", 170, 70, 50)  # BMI 17,3
    assert n.goal_weight_issues("abnehmen", 170, 70, 75)  # über aktuellem Gewicht
    assert not n.goal_weight_issues("abnehmen", 170, 80, 70)


# ---------------------------------------------------------------- flexibles Wochenbudget
from datetime import date, timedelta  # noqa: E402

from core import budget  # noqa: E402


def _week():
    start = date(2026, 9, 21)  # Montag
    return [start + timedelta(days=i) for i in range(7)]


def test_budget_without_exceptions_is_flat():
    wb = budget.plan_week(_week(), 1800, 1200, {}, date(2026, 9, 21))
    assert all(d.target == 1800 for d in wb.days) and wb.total == 7 * 1800


def test_birthday_is_spread_over_remaining_days():
    week = _week()
    wb = budget.plan_week(week, 1800, 1200, {week[5]: (2700, "Geburtstag")}, week[0])
    # 900 kcal extra auf 6 Tage = 150 weniger pro Tag
    assert wb.for_day(week[5]).target == 2700
    assert wb.for_day(week[0]).target == 1650
    assert wb.total == 7 * 1800


def test_budget_respects_floor_and_past_days():
    week = _week()
    wb = budget.plan_week(week, 1400, 1200, {week[6]: (3400, "Hochzeit")}, week[4])
    assert all(d.target >= 1200 for d in wb.days)
    assert wb.for_day(week[0]).target == 1400  # Vergangenheit unverändert
    assert wb.unallocated > 0 and wb.notes


def test_feature_flags_unlocked_and_free_core():
    from core import features

    assert features.enabled("coach", "free")  # aktuell alles frei
    old = features.ALL_UNLOCKED
    try:
        features.ALL_UNLOCKED = False
        assert features.enabled("tracking", "free") and features.enabled("gewichtstrend", "free")
        assert not features.enabled("coach", "free") and features.enabled("coach", "premium")
    finally:
        features.ALL_UNLOCKED = old
