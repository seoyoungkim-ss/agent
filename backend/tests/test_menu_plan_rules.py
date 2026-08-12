"""§77: 주간 식단표 규칙 검증 순수함수 — 키워드 판정과 경계값(정확히 4개=통과,
5개=위반, 해장 0개=위반)을 DB 없이 확인한다."""

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


def _slot(menu_name: str, day_offset: int = 0, corner_name: str = "한식") -> MenuPlanSlotItem:
    return MenuPlanSlotItem(menu_name=menu_name, corner_name=corner_name, plan_date=MONDAY + dt.timedelta(days=day_offset))


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
# 경계값
# ---------------------------------------------------------------------------


def test_check_hangover_rule_fails_with_zero_matches():
    result = check_hangover_rule([_slot("제육볶음"), _slot("된장찌개")])
    assert result.ok is False
    assert result.count == 0
    assert result.limit is None


def test_check_hangover_rule_passes_with_one_match():
    result = check_hangover_rule([_slot("황태해장국"), _slot("제육볶음")])
    assert result.ok is True
    assert result.count == 1
    assert result.matches == ["황태해장국(한식, 7/20)"]


def test_check_noodle_rule_passes_at_exactly_the_limit():
    slots = [_slot("라면", i) for i in range(4)]
    result = check_noodle_rule(slots, limit=4)
    assert result.ok is True
    assert result.count == 4


def test_check_noodle_rule_fails_over_the_limit():
    slots = [_slot("라면", i) for i in range(5)]
    result = check_noodle_rule(slots, limit=4)
    assert result.ok is False
    assert result.count == 5
    assert len(result.matches) == 5


def test_check_spicy_red_broth_rule_passes_at_exactly_the_limit():
    slots = [_slot("김치찌개", i) for i in range(4)]
    result = check_spicy_red_broth_rule(slots, limit=4)
    assert result.ok is True


def test_check_spicy_red_broth_rule_fails_over_the_limit():
    slots = [_slot("김치찌개", i) for i in range(5)]
    result = check_spicy_red_broth_rule(slots, limit=4)
    assert result.ok is False
    assert result.count == 5
