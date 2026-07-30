import datetime as dt

from app.services.menu_throughput import (
    DayThroughput,
    compute_menu_throughput_summary,
    compute_peak_share_ratio,
    window_minutes,
)


def test_computes_average_throughput_per_menu_sorted_slowest_first():
    days = [
        DayThroughput(date=dt.date(2026, 7, 6), menu_id=1, throughput=4.0),
        DayThroughput(date=dt.date(2026, 7, 13), menu_id=1, throughput=4.0),
        DayThroughput(date=dt.date(2026, 7, 7), menu_id=2, throughput=1.0),
        DayThroughput(date=dt.date(2026, 7, 14), menu_id=2, throughput=1.0),
    ]

    summary = compute_menu_throughput_summary(days)

    assert summary.overall_avg_throughput == 2.5
    assert [e.menu_id for e in summary.menus] == [2, 1]  # 느린(값이 작은) 메뉴 먼저
    assert summary.menus[0].avg_throughput == 1.0
    assert summary.menus[0].day_count == 2
    assert summary.menus[1].avg_throughput == 4.0


def test_excludes_menus_below_min_day_count():
    days = [
        DayThroughput(date=dt.date(2026, 7, 6), menu_id=1, throughput=2.0),  # 1회만 등장
        DayThroughput(date=dt.date(2026, 7, 7), menu_id=2, throughput=3.0),
        DayThroughput(date=dt.date(2026, 7, 14), menu_id=2, throughput=3.0),
    ]

    summary = compute_menu_throughput_summary(days, min_day_count=2)

    assert [e.menu_id for e in summary.menus] == [2]
    # baseline은 표본 부족 필터와 무관하게 모든 날을 포함
    assert summary.overall_avg_throughput == (2.0 + 3.0 + 3.0) / 3


def test_days_without_menu_link_excluded_from_menu_breakdown_but_kept_in_baseline():
    days = [
        DayThroughput(date=dt.date(2026, 7, 6), menu_id=None, throughput=5.0),
        DayThroughput(date=dt.date(2026, 7, 7), menu_id=1, throughput=1.0),
        DayThroughput(date=dt.date(2026, 7, 14), menu_id=1, throughput=1.0),
    ]

    summary = compute_menu_throughput_summary(days, min_day_count=2)

    assert summary.overall_avg_throughput == (5.0 + 1.0 + 1.0) / 3
    assert [e.menu_id for e in summary.menus] == [1]


def test_empty_days_returns_no_baseline_and_no_menus():
    summary = compute_menu_throughput_summary([])
    assert summary.overall_avg_throughput is None
    assert summary.menus == []


def test_window_minutes_computes_duration_between_two_times():
    assert window_minutes("11:40:00", "12:20:00") == 40.0
    assert window_minutes("11:20:00", "13:00:00") == 100.0


def test_window_minutes_floors_at_one_minute():
    assert window_minutes("12:00:00", "12:00:00") == 1.0


def test_compute_peak_share_ratio_divides_peak_by_meal_total():
    assert compute_peak_share_ratio(20, 100) == 0.2


def test_compute_peak_share_ratio_none_when_no_meal_data():
    assert compute_peak_share_ratio(0, 0) is None
