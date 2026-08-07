"""이미 태깅된 food_vector를 최신 규칙으로 다시 계산 (2026-08).

`tag_food_vector_from_name`의 규칙표를 고쳐도(예: "탕수육"이 "탕"을 포함한다고
국물로 오태깅되던 버그) **이미 저장된 food_vector는 저절로 안 바뀐다** — 이
스크립트가 갱신한다.
"""

from app.maintenance.retag_food_vector_with_rules import retag
from app.models.enums import FoodVectorSource
from app.models.master import MenuMaster
from app.services.food_vector import FOOD_VECTOR_DIMENSIONS
from app.services.food_vector_tagging import tag_food_vector_from_name

_SOUP_INDEX = FOOD_VECTOR_DIMENSIONS.index("soup_based")


def _stale_soup_vector() -> list[float]:
    """옛 규칙(바른 "탕"이 국물로 걸리던 시절)으로 계산됐다고 가정한 벡터."""
    vector = [0.2] * len(FOOD_VECTOR_DIMENSIONS)
    vector[_SOUP_INDEX] = 0.85
    return vector


def test_retags_menu_with_stale_rule_based_vector(db_session):
    """신고 재현 — "탕수육"이 옛 규칙으로 이미 국물(soup_based) 태깅돼 저장돼 있었다."""
    menu = MenuMaster(
        menu_name="탕수육",
        food_vector=_stale_soup_vector(),
        food_vector_source=FoodVectorSource.RULE,
    )
    db_session.add(menu)
    db_session.commit()

    retag(db_session, apply=True)

    db_session.refresh(menu)
    assert menu.food_vector[_SOUP_INDEX] < 0.6
    assert menu.food_vector_source == FoodVectorSource.RULE


def test_manual_override_is_never_touched(db_session):
    """관리자가 손으로 조정한 값은 규칙이 뭐라 하든 그대로 둔다."""
    manual_vector = _stale_soup_vector()
    menu = MenuMaster(
        menu_name="탕수육",
        food_vector=manual_vector,
        food_vector_source=FoodVectorSource.MANUAL,
    )
    db_session.add(menu)
    db_session.commit()

    changed = retag(db_session, apply=True)

    assert changed == 0
    db_session.refresh(menu)
    assert menu.food_vector[_SOUP_INDEX] == 0.85


def test_vector_already_matching_current_rules_is_left_alone(db_session):
    vector, _ = tag_food_vector_from_name("김치찌개")
    menu = MenuMaster(menu_name="김치찌개", food_vector=vector, food_vector_source=FoodVectorSource.RULE)
    db_session.add(menu)
    db_session.commit()

    changed = retag(db_session, apply=True)

    assert changed == 0


def test_llm_tagged_menu_that_now_matches_a_rule_is_upgraded_to_rule(db_session):
    """LLM이 채웠던 값이라도, 규칙이 새로 잡아내면 규칙 우선순위로 갱신한다."""
    menu = MenuMaster(
        menu_name="탕수육",
        food_vector=_stale_soup_vector(),
        food_vector_source=FoodVectorSource.LLM,
    )
    db_session.add(menu)
    db_session.commit()

    retag(db_session, apply=True)

    db_session.refresh(menu)
    assert menu.food_vector_source == FoodVectorSource.RULE
    assert menu.food_vector[_SOUP_INDEX] < 0.6


def test_dry_run_changes_nothing(db_session):
    menu = MenuMaster(
        menu_name="탕수육",
        food_vector=_stale_soup_vector(),
        food_vector_source=FoodVectorSource.RULE,
    )
    db_session.add(menu)
    db_session.commit()

    retag(db_session, apply=False)

    db_session.refresh(menu)
    assert menu.food_vector[_SOUP_INDEX] == 0.85


def test_is_idempotent(db_session):
    menu = MenuMaster(
        menu_name="탕수육",
        food_vector=_stale_soup_vector(),
        food_vector_source=FoodVectorSource.RULE,
    )
    db_session.add(menu)
    db_session.commit()

    retag(db_session, apply=True)
    assert retag(db_session, apply=True) == 0
