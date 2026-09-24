from datetime import date, timedelta

import pytest

from core import adaptive, trend


def test_ema_smooths_and_handles_gaps():
    pts = [(date(2026, 1, 1), 80.0), (date(2026, 1, 2), 81.0)]
    s = trend.ema_series(pts)
    assert s[0].trend == 80.0
    assert s[1].trend == pytest.approx(80.1)
    # Nach 7 Tagen Pause zählt der neue Wert stärker
    s2 = trend.ema_series([(date(2026, 1, 1), 80.0), (date(2026, 1, 8), 81.0)])
    assert s2[1].trend == pytest.approx(80 + (1 - 0.9**7))


def test_weekly_rate_detects_loss():
    start = date(2026, 1, 1)
    pts = [(start + timedelta(days=i), 90 - 0.1 * i) for i in range(30)]  # −0,7 kg/Woche
    rate = trend.weekly_rate(trend.ema_series(pts))
    assert rate is not None and -0.8 < rate < -0.4


def _history(days=28, intake=2000, loss_per_day=0.05):
    end = date(2026, 3, 1)
    start = end - timedelta(days=days + 20)
    weights = [(start + timedelta(days=i), 90 - loss_per_day * i) for i in range(days + 21)]
    intakes = {end - timedelta(days=i): intake for i in range(days)}
    return end, weights, intakes


def test_adaptive_moves_towards_observed():
    # 0,05 kg/Tag Verlust bei 2000 kcal → beobachtet ≈ 2000 + 385 = 2385
    end, weights, intakes = _history()
    est = adaptive.estimate_tdee(weights=weights, intakes=intakes, window_end=end, formula_tdee=2200,
                                 previous_tdee=None, bmr=1700)
    assert est.method == "adaptiv"
    assert 2385 - 60 < est.details["observed"] < 2385 + 60
    assert 2200 < est.tdee <= 2200 + adaptive.MAX_FIRST_CHANGE


def test_adaptive_weekly_change_is_capped():
    end, weights, intakes = _history(intake=1500, loss_per_day=0.0)
    est = adaptive.estimate_tdee(weights=weights, intakes=intakes, window_end=end, formula_tdee=2500,
                                 previous_tdee=2500, previous_method="adaptiv", bmr=1600)
    assert est.tdee == pytest.approx(2500 - adaptive.MAX_WEEKLY_CHANGE)


def test_adaptive_needs_enough_data():
    end, weights, intakes = _history()
    few = dict(list(intakes.items())[:5])
    est = adaptive.estimate_tdee(weights=weights, intakes=few, window_end=end, formula_tdee=2200,
                                 previous_tdee=None, bmr=1700)
    assert est.method == "formel" and est.tdee == 2200
    assert "getrackte Tage" in est.explanation


def test_incomplete_days_are_ignored():
    end, weights, intakes = _history()
    intakes[end] = 300  # offensichtlich unvollständig
    est = adaptive.estimate_tdee(weights=weights, intakes=intakes, window_end=end, formula_tdee=2200,
                                 previous_tdee=None, bmr=1700)
    assert est.details["logged_days"] == 27
