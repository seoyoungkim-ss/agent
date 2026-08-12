"""§77~§78: 주간 식단표 규칙 검증 순수함수 — 키워드 판정과 요일별(하루 기준,
주중만) 경계값을 DB 없이 확인한다.

§78부터 해장/면류/매운(빨간국물)은 한 주 합산이 아니라 그날 하루의 매치
개수만 본다 — "같은 날 5개=위반"과 "5일에 걸쳐 하루 1개씩=매일 통과"를
구분하는 게 이번 재설계의 핵심이라 두 케이스를 각각 테스트한다."""

import datetime as dt

from app.services.menu_plan_rules import (
    MenuPlanSlotItem,
    check_hangover_rule,
    check_noodle_rule,
    check_spicy_red_broth_rule,
    is_hangover_dish,
    is_noodle_dish,
    is_spicy_red_broth_dish,
)

MONDAY = dt.date(2026, 7, 20)
SATURDAY = MONDAY + dt.timedelta(days=5)
SUNDAY = MONDAY + dt.timedelta(days=6)


def _slot(menu_name: str, day_offset: int = 0, corner_id: int = 1, corner_name: str = "한식") -> MenuPlanSlotItem:
    return MenuPlanSlotItem(
        menu_name=menu_name, corner_id=corner_id, corner_name=corner_name, plan_date=MONDAY + dt.timedelta(days=day_offset)
    )


# ---------------------------------------------------------------------------
# 키워드 판정
# ---------------------------------------------------------------------------


def test_is_hangover_dish_matches_known_keywords():
    assert is_hangover_dish("황태해장국")
    assert is_hangover_dish("북엇국")
    assert not is_hangover_dish("제육볶음")


def test_is_noodle_dish_matches_ramen_and_other_noodles():
    assert is_noodle_dish("라면")
    assert is_noodle_dish("우동")
    assert is_noodle_dish("짜장면")
    assert is_noodle_dish("냉면")
    assert not is_noodle_dish("흰쌀밥")  # carb 차원엔 걸리지만 면류는 아니다


def test_is_spicy_red_broth_dish_requires_both_spicy_and_soup():
    assert is_spicy_red_broth_dish("김치찌개")  # spicy(김치) + soup_based(찌개)
    assert not is_spicy_red_broth_dish("탕수육")  # spicy 아님, soup_based도 아님(접미어 불일치)
    assert not is_spicy_red_broth_dish("불닭볶음면")  # spicy(불닭)만 걸리고 국물 아님(면류 볶음)


# ---------------------------------------------------------------------------
# 요일별(하루 기준) 판정 — §78 핵심 변경
# ---------------------------------------------------------------------------


def test_check_hangover_rule_flags_only_the_day_without_a_hangover_dish():
    slots = [_slot("황태해장국", 0), _slot("제육볶음", 1)]  # 월: 해장 있음, 화: 없음
    results = check_hangover_rule(slots)
    by_date = {r.plan_date: r for r in results}
    assert len(results) == 2
    assert by_date[MONDAY].ok is True
    assert by_date[MONDAY].count == 1
    assert by_date[MONDAY + dt.timedelta(days=1)].ok is False
    assert by_date[MONDAY + dt.timedelta(days=1)].count == 0


def test_check_noodle_rule_passes_when_spread_across_different_days():
    """5개를 5일에 걸쳐 하루 1개씩 편성하면(§77의 전제였던 "이번 주에 5번") 이제는
    매일 통과해야 한다 — 하루 기준으로 바뀐 게 핵심이라 이 케이스가 회귀 방지선."""
    slots = [_slot("라면", i) for i in range(5)]  # 월~금 하루 1개씩
    results = check_noodle_rule(slots, limit=4)
    assert len(results) == 5
    assert all(r.ok is True and r.count == 1 for r in results)


def test_check_noodle_rule_fails_when_five_are_on_the_same_day():
    slots = [_slot("라면", 0, corner_id=i) for i in range(5)]  # 전부 월요일, 코너만 다름
    results = check_noodle_rule(slots, limit=4)
    assert len(results) == 1
    assert results[0].plan_date == MONDAY
    assert results[0].ok is False
    assert results[0].count == 5
    assert len(results[0].matches) == 5


def test_check_noodle_rule_passes_at_exactly_the_limit_same_day():
    slots = [_slot("라면", 0, corner_id=i) for i in range(4)]
    results = check_noodle_rule(slots, limit=4)
    assert results[0].ok is True
    assert results[0].count == 4


def test_check_spicy_red_broth_rule_same_day_boundary():
    ok_slots = [_slot("김치찌개", 0, corner_id=i) for i in range(4)]
    assert check_spicy_red_broth_rule(ok_slots, limit=4)[0].ok is True

    over_slots = [_slot("김치찌개", 0, corner_id=i) for i in range(5)]
    result = check_spicy_red_broth_rule(over_slots, limit=4)[0]
    assert result.ok is False
    assert result.count == 5


def test_weekday_only_rules_exclude_saturday_and_sunday():
    slots = [_slot("라면", 5, corner_id=i) for i in range(5)] + [_slot("라면", 6, corner_id=i) for i in range(5)]
    assert check_noodle_rule(slots, limit=4) == []


def test_daily_result_matches_carry_corner_and_date_for_grid_highlight():
    """프론트가 위반 메뉴 클릭 시 격자표 셀(`${plan_date}_${corner_id}`)을
    바로 찾을 수 있어야 하므로 match에 corner_id/plan_date가 들어있어야 한다."""
    slots = [_slot("황태해장국", 0, corner_id=7, corner_name="한식")]
    result = check_hangover_rule(slots)[0]
    match = result.matches[0]
    assert match.menu_name == "황태해장국"
    assert match.corner_id == 7
    assert match.corner_name == "한식"
    assert match.plan_date == MONDAY
