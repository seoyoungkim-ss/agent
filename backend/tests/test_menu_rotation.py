import datetime as dt

from app.services.menu_rotation import (
    RotationFlag,
    build_corner_menu_dates,
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
        (d(1), "한식", "김치", "부찬"),
        (d(2), "한식", "김치", "부찬"),
        (d(3), "한식", "김치", "부찬"),
        (d(4), "한식", "김치", "부찬"),
        (d(1), "한식", "돈까스", "메인"),
        (d(5), "한식", "돈까스", "메인"),
    ]
    result = find_overused_menus(planned, threshold=3)
    assert [o.menu_name for o in result] == ["김치"]
    assert result[0].count == 4
    assert result[0].menu_role == "부찬"
    assert result[0].corner_name == "한식"


def test_find_overused_menus_counts_across_roles():
    """같은 나물이 부찬/건강가든으로 흩어져도 먹는 사람에겐 중복이다."""
    planned = [
        (d(1), "한식", "시금치나물", "부찬"),
        (d(2), "한식", "시금치나물", "건강가든"),
        (d(3), "한식", "시금치나물", "건강가든"),
        (d(4), "한식", "시금치나물", "건강가든"),
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


# ---------------------------------------------------------------------------
# 과다 편성 횟수는 행이 아니라 고유 날짜로 센다 (2026-08 신고)
# ---------------------------------------------------------------------------
# "중복점검에서도 같은날 메뉴가 두번씩 카운트됨". 원인은 find_overused_menus가
# len(entries)로 행을 센 것 — 바로 아래 count_in_window는 처음부터 날짜 집합으로
# 세고 있어서 **같은 모듈 안에서 규칙이 반대**였다.


def test_same_menu_on_the_same_day_in_two_corners_counts_once():
    """한 날에 두 코너에 깔린 건 하루치 노출이다 — 2회가 아니다.

    같은 날 중복이 안 보이게 되는 건 아니다: SAME_DAY 플래그가 그 축을 담당한다.
    """
    planned = [
        (dt.date(2026, 7, 6), "한식", "김치", "부찬"),
        (dt.date(2026, 7, 6), "한식", "김치", "부찬"),  # 같은 코너에 중복 행
        (dt.date(2026, 7, 7), "한식", "김치", "부찬"),
    ]
    result = find_overused_menus(planned, threshold=1)
    assert len(result) == 1
    assert result[0].count == 2, "고유 날짜 2일이어야 하는데 행 수(3)로 셌다"
    assert result[0].dates == [dt.date(2026, 7, 6), dt.date(2026, 7, 7)]


def test_duplicate_rows_do_not_inflate_the_count():
    """DB에 중복 행이 남아 있어도 편성 횟수가 부풀지 않아야 한다."""
    planned = [(dt.date(2026, 7, 6), "한식", "김치", "부찬")] * 5
    assert find_overused_menus(planned, threshold=1) == []


def test_threshold_is_applied_to_unique_days():
    """임계 비교도 고유 날짜 기준이라야 일관된다."""
    same_day = [(dt.date(2026, 7, 6), "한식", "김치", "부찬")] * 3
    assert find_overused_menus(same_day, threshold=2) == []

    three_days = [
        (dt.date(2026, 7, 6), "한식", "김치", "부찬"),
        (dt.date(2026, 7, 7), "한식", "김치", "부찬"),
        (dt.date(2026, 7, 8), "한식", "김치", "부찬"),
    ]
    assert len(find_overused_menus(three_days, threshold=2)) == 1


def test_overuse_count_agrees_with_count_in_window():
    """같은 화면의 두 숫자가 서로 다른 규칙이면 담당자가 못 믿는다."""
    dates = [dt.date(2026, 7, 6), dt.date(2026, 7, 6), dt.date(2026, 7, 20)]
    planned = [(d, "한식", "김치", "부찬") for d in dates]
    overused = find_overused_menus(planned, threshold=1)
    assert overused[0].count == count_in_window(dt.date(2026, 7, 20), dates)


# ---------------------------------------------------------------------------
# 중복은 코너 안에서 — 건강가든만 예외 (2026-08 담당자 기준)
# ---------------------------------------------------------------------------
# "중복은 코너 안에서 봐야함 포기김치가 다른 코너에서 각각 나왔다고 중복이면
#  안되고 건강가든하고만 중복 봐야함"


def test_same_menu_in_different_corners_is_not_overuse():
    """한식 포기김치와 분식 포기김치는 서로 다른 선택지다."""
    planned = [
        (d(1), "한식", "포기김치", "부찬"),
        (d(2), "분식", "포기김치", "부찬"),
        (d(3), "양식", "포기김치", "부찬"),
        (d(4), "일품", "포기김치", "부찬"),
    ]
    assert find_overused_menus(planned, threshold=3) == []


def test_repetition_inside_one_corner_is_overuse():
    """같은 코너에서 반복되면 그건 중복이 맞다."""
    planned = [(d(i), "한식", "포기김치", "부찬") for i in range(1, 5)]
    result = find_overused_menus(planned, threshold=3)
    assert [(o.corner_name, o.menu_name, o.count) for o in result] == [("한식", "포기김치", 4)]


def test_health_garden_counts_against_every_corner():
    """건강가든은 공용이라 어느 코너 부찬과 겹쳐도 중복이다."""
    planned = [
        (d(1), "한식", "시금치나물", "부찬"),
        (d(2), "한식", "시금치나물", "부찬"),
        (d(3), "그린미트", "시금치나물", "건강가든"),
        (d(4), "그린미트", "시금치나물", "건강가든"),
    ]
    result = find_overused_menus(planned, threshold=3)
    corners = {o.corner_name for o in result}
    assert "한식" in corners, "건강가든 등장이 한식 부찬 반복에 합쳐지지 않았다"
    assert all(o.count == 4 for o in result)


def test_health_garden_only_menu_does_not_explode_into_every_corner_falsely():
    """건강가든에만 있고 다른 코너엔 없으면, 그 자체의 반복만 잡혀야 한다."""
    planned = [
        (d(1), "한식", "제육볶음", "메인"),  # 코너 목록에 한식이 들어가게 하는 행
        *[(d(i), "그린미트", "샐러드", "건강가든") for i in range(1, 5)],
    ]
    result = find_overused_menus(planned, threshold=3)
    assert {o.menu_name for o in result} == {"샐러드"}
    assert all(o.count == 4 for o in result)


def test_build_corner_menu_dates_keeps_same_day_duplicate_for_clash_detection():
    """SAME_DAY 판정이 살아 있어야 하므로 같은 날짜 중복을 남긴다.

    같은 코너 부찬 + 같은 날 건강가든 → 날짜가 두 번 들어가 SAME_DAY로 잡힌다.
    다른 코너끼리는 각 코너에 한 번씩만 들어가 안 잡힌다.
    """
    dates = build_corner_menu_dates(
        [
            (d(1), "한식", "시금치나물", "부찬"),
            (d(1), "그린미트", "시금치나물", "건강가든"),
        ]
    )
    assert dates[("한식", "시금치나물")] == [d(1), d(1)]  # 겹침 → SAME_DAY

    dates2 = build_corner_menu_dates(
        [
            (d(1), "한식", "포기김치", "부찬"),
            (d(1), "분식", "포기김치", "부찬"),
        ]
    )
    assert dates2[("한식", "포기김치")] == [d(1)]
    assert dates2[("분식", "포기김치")] == [d(1)]

