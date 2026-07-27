import datetime as dt

import pytest

from app.models.enums import MenuQuadrant, TasteScore
from app.services.menu_performance import (
    DeclineDiagnosis,
    TrendDirection,
    classify_menu_quadrant,
    compute_menu_frequency,
    compute_menu_score,
    compute_share_of_traffic,
    diagnose_headcount_decline,
)

# ---- 6.3.1 점수화 + 표본 보정 ----


def test_raw_score_conversion_5_3_1():
    result = compute_menu_score(
        [TasteScore.DELICIOUS, TasteScore.NORMAL, TasteScore.NEEDS_IMPROVEMENT],
        global_avg_score=3.0,
        shrinkage_m=20,
        low_sample_threshold=10,
    )
    assert result.raw_score == pytest.approx((5 + 3 + 1) / 3)


def test_low_sample_menu_is_pulled_toward_global_average():
    # 평가 2건뿐인데 우연히 둘 다 맛남(5점)인 경우 -> raw_score=5.0이지만
    # adjusted_score는 global_avg_score 쪽으로 크게 당겨져야 한다.
    result = compute_menu_score(
        [TasteScore.DELICIOUS, TasteScore.DELICIOUS],
        global_avg_score=3.0,
        shrinkage_m=20,
        low_sample_threshold=10,
    )
    assert result.raw_score == 5.0
    assert result.adjusted_score < 3.5  # 대부분 global_avg(3.0) 쪽으로 수렴
    assert result.is_low_sample is True


def test_high_sample_menu_stays_close_to_raw_score():
    scores = [TasteScore.DELICIOUS] * 100
    result = compute_menu_score(
        scores, global_avg_score=3.0, shrinkage_m=20, low_sample_threshold=10
    )
    assert result.adjusted_score > 4.5  # 표본이 충분하면 raw_score(5.0)에 가까워짐
    assert result.is_low_sample is False


def test_zero_evaluations_returns_global_average_and_low_sample():
    result = compute_menu_score(
        [], global_avg_score=3.2, shrinkage_m=20, low_sample_threshold=10
    )
    assert result.evaluation_count == 0
    assert result.raw_score is None
    assert result.adjusted_score == 3.2
    assert result.is_low_sample is True


# ---- 6.3.2 빈도 ----


def test_menu_frequency_basic():
    dates = [dt.date(2026, 1, 1), dt.date(2026, 1, 8), dt.date(2026, 1, 15)]
    freq = compute_menu_frequency(dates, total_headcount=300, evaluation_count=90)
    assert freq.appearance_count == 3
    assert freq.avg_recurrence_interval_days == pytest.approx(7.0)
    assert freq.evaluation_rate == pytest.approx(0.3)
    assert freq.last_appearance == dt.date(2026, 1, 15)


def test_menu_frequency_deduplicates_same_day_multiple_logs():
    dates = [dt.date(2026, 1, 1)] * 50 + [dt.date(2026, 1, 8)] * 30
    freq = compute_menu_frequency(dates, total_headcount=80, evaluation_count=10)
    assert freq.appearance_count == 2


def test_menu_frequency_single_appearance_has_no_interval():
    freq = compute_menu_frequency([dt.date(2026, 1, 1)], total_headcount=10, evaluation_count=2)
    assert freq.avg_recurrence_interval_days is None


def test_menu_frequency_zero_headcount_no_rate():
    freq = compute_menu_frequency([], total_headcount=0, evaluation_count=0)
    assert freq.evaluation_rate is None
    assert freq.last_appearance is None


# ---- 6.3.3 하락 원인 진단 ----


def test_share_of_traffic():
    assert compute_share_of_traffic(30, 300) == pytest.approx(0.1)
    assert compute_share_of_traffic(10, 0) is None


@pytest.mark.parametrize(
    "share_trend,satisfaction_trend,expected",
    [
        (TrendDirection.DOWN, TrendDirection.DOWN, DeclineDiagnosis.MENU_SATISFACTION_ISSUE),
        (TrendDirection.DOWN, TrendDirection.UP, DeclineDiagnosis.SUBSTITUTION_RISK),
        (TrendDirection.DOWN, TrendDirection.FLAT, DeclineDiagnosis.SUBSTITUTION_RISK),
        (TrendDirection.FLAT, TrendDirection.DOWN, DeclineDiagnosis.LATENT_CHURN_RISK),
        (TrendDirection.UP, TrendDirection.DOWN, DeclineDiagnosis.LATENT_CHURN_RISK),
        (TrendDirection.FLAT, TrendDirection.FLAT, DeclineDiagnosis.EXTERNAL_TRAFFIC_ISSUE),
        (TrendDirection.UP, TrendDirection.UP, DeclineDiagnosis.EXTERNAL_TRAFFIC_ISSUE),
    ],
)
def test_diagnose_headcount_decline_matrix(share_trend, satisfaction_trend, expected):
    assert diagnose_headcount_decline(share_trend, satisfaction_trend) == expected


# ---- 6.3.4 4분면 ----


def test_quadrant_popular():
    q = classify_menu_quadrant(
        demand=10,
        satisfaction=4.5,
        demand_threshold=5,
        satisfaction_threshold=3.5,
        evaluation_count=50,
        low_sample_threshold=10,
    )
    assert q == MenuQuadrant.POPULAR


def test_quadrant_needs_improvement():
    q = classify_menu_quadrant(
        demand=10,
        satisfaction=2.5,
        demand_threshold=5,
        satisfaction_threshold=3.5,
        evaluation_count=50,
        low_sample_threshold=10,
    )
    assert q == MenuQuadrant.NEEDS_IMPROVEMENT


def test_quadrant_hidden_gem():
    q = classify_menu_quadrant(
        demand=2,
        satisfaction=4.5,
        demand_threshold=5,
        satisfaction_threshold=3.5,
        evaluation_count=50,
        low_sample_threshold=10,
    )
    assert q == MenuQuadrant.HIDDEN_GEM


def test_quadrant_removal_candidate():
    q = classify_menu_quadrant(
        demand=2,
        satisfaction=2.0,
        demand_threshold=5,
        satisfaction_threshold=3.5,
        evaluation_count=50,
        low_sample_threshold=10,
    )
    assert q == MenuQuadrant.REMOVAL_CANDIDATE


def test_quadrant_low_sample_overrides_everything():
    q = classify_menu_quadrant(
        demand=10,
        satisfaction=5.0,
        demand_threshold=5,
        satisfaction_threshold=3.5,
        evaluation_count=3,
        low_sample_threshold=10,
    )
    assert q == MenuQuadrant.LOW_SAMPLE
