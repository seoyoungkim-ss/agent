import datetime as dt

from app.services.menu_rotation import (
    RotationFlag,
    average_interval_days,
    classify_rotation,
    count_in_window,
    find_overused_menus,
    is_over_frequency,
    max_in_window_for_role,
)


def d(day: int) -> dt.date:
    return dt.date(2026, 8, 1) + dt.timedelta(days=day - 1)


def test_average_interval_needs_two_appearances():
    assert average_interval_days([]) is None
    assert average_interval_days([d(1)]) is None
    assert average_interval_days([d(1), d(15)]) == 14.0
    # 중복 날짜는 하나로 본다(같은 날 여러 코너 편성이 주기를 왜곡하면 안 됨)
    assert average_interval_days([d(1), d(1), d(15)]) == 14.0


def test_first_time_when_no_prior_appearance():
    v = classify_rotation(d(10), [])
    assert v.flag == RotationFlag.FIRST_TIME
    assert v.gap_days is None
    assert v.previous_date is None


def test_same_day_duplicate_across_corners():
    # 같은 날짜가 두 번 들어오면 다른 코너/끼니에 중복 편성된 것
    v = classify_rotation(d(10), [d(10), d(10)])
    assert v.flag == RotationFlag.SAME_DAY
    assert v.gap_days == 0


def test_too_soon_when_under_absolute_minimum():
    v = classify_rotation(d(10), [d(1)])  # 9일 만에 재등장
    assert v.flag == RotationFlag.TOO_SOON
    assert v.gap_days == 9


def test_normal_when_gap_matches_usual_cycle():
    # 과거 14일 주기 → 이번에도 14일 만에 등장
    v = classify_rotation(d(29), [d(1), d(15)])
    assert v.flag == RotationFlag.NORMAL
    assert v.gap_days == 14
    assert v.avg_interval_days == 14.0


def test_early_when_much_sooner_than_usual_cycle():
    # 과거 60일 주기였는데 20일 만에 등장 — 절대 기준(14일)은 통과하지만 이례적
    past = [dt.date(2026, 1, 1), dt.date(2026, 3, 2), dt.date(2026, 5, 1)]
    v = classify_rotation(dt.date(2026, 5, 21), past)
    assert v.flag == RotationFlag.EARLY
    assert v.gap_days == 20


def test_long_absent_when_far_beyond_usual_cycle():
    # 과거 14일 주기였는데 60일 만에 등장
    v = classify_rotation(dt.date(2026, 4, 15), [dt.date(2026, 2, 1), dt.date(2026, 2, 15)])
    assert v.flag == RotationFlag.LONG_ABSENT


def test_avg_interval_excludes_the_appearance_being_judged():
    """이번 등장을 평균에 넣으면 자기 자신이 기준을 끌어내려 항상 정상이 된다."""
    past = [dt.date(2026, 1, 1), dt.date(2026, 3, 2), dt.date(2026, 5, 1)]
    v = classify_rotation(dt.date(2026, 5, 21), past)
    # 과거끼리의 간격(60, 60)만 평균 → 60일. 이번 20일이 섞이면 46.7로 떨어져
    # EARLY 판정이 뒤집힌다.
    assert v.avg_interval_days == 60.0


def test_find_overused_menus_respects_threshold():
    planned = [
        (d(1), "김치", "부찬"),
        (d(2), "김치", "부찬"),
        (d(3), "김치", "부찬"),
        (d(4), "김치", "부찬"),
        (d(1), "돈까스", "메인"),
        (d(5), "돈까스", "메인"),
    ]
    result = find_overused_menus(planned, threshold=3)
    assert [o.menu_name for o in result] == ["김치"]
    assert result[0].count == 4
    assert result[0].menu_role == "부찬"


def test_find_overused_menus_counts_across_roles():
    """같은 나물이 부찬/건강가든으로 흩어져도 먹는 사람에겐 중복이다."""
    planned = [
        (d(1), "시금치나물", "부찬"),
        (d(2), "시금치나물", "건강가든"),
        (d(3), "시금치나물", "건강가든"),
        (d(4), "시금치나물", "건강가든"),
    ]
    result = find_overused_menus(planned, threshold=3)
    assert result[0].count == 4
    assert result[0].menu_role == "건강가든"  # 최빈 역할로 대표 표기


# ---------------------------------------------------------------------------
# 편성 빈도 — 횟수 기준 (담당자: "3개월에 2회까지는 무난")
# ---------------------------------------------------------------------------


def test_count_in_window_counts_days_not_rows():
    """같은 날 두 코너에 깔린 건 1회 — "얼마나 자주 내보내나"가 질문이다."""
    dates = [d(1), d(1), d(10)]
    assert count_in_window(d(10), dates) == 2


def test_count_in_window_excludes_dates_outside_90_days():
    old = dt.date(2026, 1, 1)
    assert count_in_window(d(10), [old, d(1), d(10)]) == 2


def test_main_menu_allows_two_in_three_months():
    """담당자 기준 그대로 — 2회까지는 무난, 3회부터 과다."""
    two = [d(1), d(40)]
    assert is_over_frequency(d(40), two, "메인") is False
    three = [d(1), d(40), d(80)]
    assert is_over_frequency(d(80), three, "메인") is True


def test_side_dish_threshold_is_looser_than_main():
    """김치·나물 같은 부찬은 자주 돌려쓰는 게 정상이다."""
    four = [d(1), d(20), d(40), d(60)]
    assert is_over_frequency(d(60), four, "메인") is True
    assert is_over_frequency(d(60), four, "부찬") is False


def test_side_dish_still_flagged_when_used_too_often():
    seven = [d(1 + i * 10) for i in range(7)]
    assert is_over_frequency(seven[-1], seven, "부찬") is True


def test_health_garden_uses_side_threshold():
    """건강가든은 부찬과 같은 성격으로 본다."""
    assert max_in_window_for_role("건강가든") == max_in_window_for_role("부찬")
