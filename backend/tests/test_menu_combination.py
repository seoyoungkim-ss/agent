import datetime as dt

from app.services.menu_combination import (
    ComboDay,
    compute_combo_nutrition_profile,
    compute_combo_satisfaction_summary,
)


def test_compute_combo_satisfaction_summary_groups_by_side_combo_sorted_desc():
    days = [
        ComboDay(dt.date(2026, 7, 6), frozenset({1, 2}), avg_satisfaction=4.5),
        ComboDay(dt.date(2026, 7, 13), frozenset({1, 2}), avg_satisfaction=4.3),
        ComboDay(dt.date(2026, 7, 20), frozenset({3}), avg_satisfaction=2.0),
    ]
    summaries = compute_combo_satisfaction_summary(days)
    assert len(summaries) == 2
    assert summaries[0].side_menu_ids == frozenset({1, 2})
    assert summaries[0].day_count == 2
    assert round(summaries[0].avg_satisfaction, 2) == 4.4
    assert summaries[1].side_menu_ids == frozenset({3})


def test_compute_combo_satisfaction_summary_puts_unevaluated_combo_last():
    days = [
        ComboDay(dt.date(2026, 7, 6), frozenset({1}), avg_satisfaction=None),
        ComboDay(dt.date(2026, 7, 13), frozenset({2}), avg_satisfaction=3.0),
    ]
    summaries = compute_combo_satisfaction_summary(days)
    assert summaries[0].side_menu_ids == frozenset({2})
    assert summaries[1].avg_satisfaction is None


def test_compute_combo_satisfaction_summary_filters_by_min_day_count():
    days = [
        ComboDay(dt.date(2026, 7, 6), frozenset({1}), avg_satisfaction=4.0),
        ComboDay(dt.date(2026, 7, 13), frozenset({2}), avg_satisfaction=3.0),
        ComboDay(dt.date(2026, 7, 20), frozenset({2}), avg_satisfaction=3.5),
    ]
    summaries = compute_combo_satisfaction_summary(days, min_day_count=2)
    assert len(summaries) == 1
    assert summaries[0].side_menu_ids == frozenset({2})


def test_compute_combo_nutrition_profile_averages_dimensions():
    food_vectors = {
        1: [0.8, 0.1, 0.1, 0.1, 0.1, 0.2, 0.1, 0.1, 0.1, 0.1],  # spicy 위주
        2: [0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.1, 0.1, 0.1, 0.9],  # vegetable_ratio 위주
    }
    profile = compute_combo_nutrition_profile([1, 2], food_vectors)
    assert profile["매운맛"] == 0.5
    assert profile["채소"] == 0.5


def test_compute_combo_nutrition_profile_empty_when_no_vectors_available():
    assert compute_combo_nutrition_profile([1, 2], {}) == {}
