from app.services.food_vector import FOOD_VECTOR_DIMENSIONS
from app.services.menu_clash import (
    extract_ingredients,
    find_ingredient_clashes,
    find_vector_clashes,
)


def _vec(**dims: float) -> list[float]:
    """지정한 차원만 값을 넣고 나머지는 0.2(미매칭 기본값)로 채운다."""
    return [dims.get(d, 0.2) for d in FOOD_VECTOR_DIMENSIONS]


# ---------------------------------------------------------------------------
# 재료 중복
# ---------------------------------------------------------------------------


def test_extract_ingredients_finds_tokens_in_compound_names():
    assert extract_ingredients("콩나물국밥") == {"콩나물"}
    assert extract_ingredients("돼지고기김치찌개") == {"돼지고기", "김치"}
    assert extract_ingredients("된장찌개") == {"된장"}


def test_extract_ingredients_returns_empty_for_unknown_menu():
    assert extract_ingredients("함박스테이크") == set()


def test_extract_ingredients_has_no_single_char_false_positives():
    """1자 토큰("무")을 사전에서 뺐으므로 "무침"·"무국"에 오탐이 없어야 한다."""
    assert extract_ingredients("오이무침") == {"오이"}
    assert "무" not in extract_ingredients("무국")


def test_ingredient_clash_between_main_and_side():
    """담당자가 든 실제 예시 — 콩나물국밥(메인) + 콩나물무침(부찬)."""
    clashes = find_ingredient_clashes("콩나물국밥", ["콩나물무침", "김치"])
    assert len(clashes) == 1
    assert clashes[0].menu_a == "콩나물국밥"
    assert clashes[0].menu_b == "콩나물무침"
    assert clashes[0].shared == ["콩나물"]


def test_ingredient_clash_between_sides_only():
    """부찬끼리의 중복도 잡는다(요청: "부찬끼리 재료 또는 카테고리 중복")."""
    clashes = find_ingredient_clashes("돈까스", ["두부조림", "두부부침"])
    assert len(clashes) == 1
    assert {clashes[0].menu_a, clashes[0].menu_b} == {"두부조림", "두부부침"}
    assert clashes[0].shared == ["두부"]


def test_no_ingredient_clash_when_nothing_shared():
    assert find_ingredient_clashes("돈까스", ["김치", "미역국"]) == []


def test_ingredient_clash_works_without_main():
    """메인이 미배정인 슬롯에서도 부찬끼리는 봐야 한다."""
    clashes = find_ingredient_clashes(None, ["감자조림", "감자채볶음"])
    assert len(clashes) == 1
    assert clashes[0].shared == ["감자"]


# ---------------------------------------------------------------------------
# 특성(카테고리) 중복
# ---------------------------------------------------------------------------


def test_vector_clash_detects_shared_spicy():
    """담당자 예시 — 순두부찌개(매움) + 매운양념 부찬(매움)."""
    clashes, untagged = find_vector_clashes(
        ("순두부찌개", _vec(spicy=0.85, soup_based=0.85)),
        [("매운어묵볶음", _vec(spicy=0.85))],
    )
    assert untagged == []
    dims = {c.dimension for c in clashes}
    assert "spicy" in dims
    spicy = next(c for c in clashes if c.dimension == "spicy")
    assert spicy.label_ko == "매운맛"


def test_vector_clash_detects_shared_carb():
    """담당자 예시 — 메인이 탄수화물 위주인데 부찬도 탄수화물."""
    clashes, _ = find_vector_clashes(
        ("잔치국수", _vec(carb=0.85)),
        [("떡볶이", _vec(carb=0.85))],
    )
    assert [c.dimension for c in clashes] == ["carb"]
    assert clashes[0].label_ko == "탄수화물"


def test_protein_and_vegetable_overlap_is_not_a_clash():
    """단백질·채소가 겹치는 건 문제가 아니라 오히려 좋다 — 충돌로 안 본다."""
    clashes, _ = find_vector_clashes(
        ("제육볶음", _vec(protein=0.85, vegetable_ratio=0.85)),
        [("두부조림", _vec(protein=0.85, vegetable_ratio=0.85))],
    )
    assert clashes == []


def test_vector_clash_needs_both_sides_above_threshold():
    clashes, _ = find_vector_clashes(
        ("김치찌개", _vec(spicy=0.85)),
        [("계란찜", _vec(spicy=0.2))],
    )
    assert clashes == []


def test_untagged_menus_are_reported_not_silently_passed():
    """food_vector가 없는 메뉴를 조용히 '충돌 없음'으로 넘기면 안 된다."""
    clashes, untagged = find_vector_clashes(
        ("신메뉴A", None),
        [("김치", _vec(spicy=0.85)), ("신메뉴B", None)],
    )
    assert clashes == []
    assert untagged == ["신메뉴A", "신메뉴B"]


def test_vector_clash_between_sides_only():
    clashes, _ = find_vector_clashes(
        ("돈까스", _vec()),
        [("감자튀김", _vec(fried=0.85)), ("고구마튀김", _vec(fried=0.85))],
    )
    assert [c.dimension for c in clashes] == ["fried"]
    assert {clashes[0].menu_a, clashes[0].menu_b} == {"감자튀김", "고구마튀김"}
