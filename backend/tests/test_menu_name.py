"""메뉴명 원산지 정규화.

⚠️ 이 케이스 표는 `ingestion-tool/tests/test_weekly_menu_parser.py`의
`ORIGIN_CASES`와 **같은 내용이어야 한다.** 두 패키지가 코드를 공유할 수 없어
판정 로직이 복제돼 있고, 2026-08까지 실제로 어긋나 있었다(양쪽 다 콜론만
인정해 `(계육-국산)`을 놓쳤다). 한쪽만 고치면 여기서 깨지도록 둔다.
"""

import pytest

from app.services.food_vector import FOOD_VECTOR_DIMENSIONS
from app.services.food_vector_tagging import tag_food_vector_from_name
from app.services.menu_name import (
    is_origin_annotation_text,
    match_key,
    pair_likely_same_menu,
    strip_origin_annotation,
)

# (입력, 통째로 원산지인가, 주석 제거 후 이름)
ORIGIN_CASES = [
    # 실사용 신고 케이스
    ("(계육-국산)", True, ""),
    ("(오징어-중국산)", True, ""),
    ("(돈육:국내산)", True, ""),
    ("(쌀:국내산, 돈육:국내산)", True, ""),
    ("*돈육:국내산", True, ""),
    ("우삼겹구이(우육:호주산)", False, "우삼겹구이"),
    ("우삼겹구이(우육:호주산, 돈육:국내산)", False, "우삼겹구이"),
    ("오징어(중국산)", False, "오징어"),
    ("계육(국산)", False, "계육"),
    # 지워지면 안 되는 것들 — 구분자를 넓히면서 생기는 오삭제 위험
    ("(오징어볶음-매운맛)", False, "(오징어볶음-매운맛)"),
    ("김치찌개(얼큰한맛)", False, "김치찌개(얼큰한맛)"),
    ("제육볶음", False, "제육볶음"),
    ("함박스테이크&소스", False, "함박스테이크&소스"),
    # 2026-08: 원산지가 아닌 재료 구성이 섞여도 통째로 주석이다
    ("(햄-계육, 돈육:국내산)", True, ""),
    ("(햄-계육)", True, ""),
    # 2026-08: 7자 원산지를 못 잡아 메뉴가 갈라졌다(연어파피요트 신고)
    ("연어파피요트(연어:노르웨이자연산)", False, "연어파피요트"),
    ("(연어스테이크-노르웨이)", False, "(연어스테이크-노르웨이)"),
]


@pytest.mark.parametrize("raw,is_annotation,_normalized", ORIGIN_CASES)
def test_is_origin_annotation_text(raw, is_annotation, _normalized):
    assert is_origin_annotation_text(raw) is is_annotation


@pytest.mark.parametrize("raw,_is_annotation,normalized", ORIGIN_CASES)
def test_strip_origin_annotation(raw, _is_annotation, normalized):
    if normalized:
        assert strip_origin_annotation(raw) == normalized


def test_origin_suffix_does_not_match_soup_keyword():
    """`soup_based`의 "국"이 "중국산"에 걸리면 그 여파가 단순 오태깅에서 안 끝난다.

    규칙이 하나라도 걸리면 food_vector가 NULL이 아니게 채워지고, LLM 보정 배치는
    `food_vector IS NULL`만 대상으로 하므로 그 행이 **영구히 보정 대상에서 빠진다**.
    """
    soup_index = FOOD_VECTOR_DIMENSIONS.index("soup_based")
    for origin in ("중국산", "외국산", "국내산", "국산", "미국산", "태국산"):
        vector, matched_any = tag_food_vector_from_name(origin)
        assert vector[soup_index] < 0.6, f"{origin}이 국물 메뉴로 태깅됐다"
        assert matched_any is False, f"{origin}이 규칙에 걸려 LLM 보정에서 제외된다"


def test_real_soup_menus_still_tagged():
    """오탐을 막느라 진짜 국물 메뉴를 놓치면 안 된다."""
    soup_index = FOOD_VECTOR_DIMENSIONS.index("soup_based")
    for menu in ("미역국", "된장국", "북어국", "김치찌개", "감자탕", "돼지국밥"):
        vector, _ = tag_food_vector_from_name(menu)
        assert vector[soup_index] >= 0.6, f"{menu}이 국물 메뉴로 안 잡힌다"


def test_tagging_ignores_origin_annotation_in_name():
    """이름에 원산지가 남아 있어도 태깅이 오염되면 안 된다."""
    plain, _ = tag_food_vector_from_name("돈까스")
    annotated, _ = tag_food_vector_from_name("돈까스(돈육:국내산)")
    assert plain == annotated


# ---------------------------------------------------------------------------
# 매칭 키 (2026-08 "연어파피요트가 매칭 안 됨" 신고)
# ---------------------------------------------------------------------------
# 표시명은 원문 그대로 두고, 조회용 키만 접는다. 이 키가 같아야 식단표와
# 취식기록이 같은 menu_master 행을 가리킨다.


@pytest.mark.parametrize(
    "variant",
    [
        "연어파피요트",
        "연어 파피요트",  # 내부 공백
        "연어  파피요트",  # 연속 공백
        " 연어파피요트 ",  # 앞뒤 공백
        "연어파피요트(연어:노르웨이산)",  # 원산지 주석
        "연어파피요트(연어:노르웨이자연산)",  # 7자 원산지 — 예전엔 못 뗐다
        "연어파피요트（연어:노르웨이산）",  # 전각 괄호
        "(포장)연어파피요트",  # POS 판매 형태 접두사
    ],
)
def test_match_key_folds_display_variants_together(variant):
    assert match_key(variant) == match_key("연어파피요트")


@pytest.mark.parametrize(
    "a,b",
    [
        ("김치찌개", "부대찌개"),
        ("김치찌개", "김치찌개(얼큰한맛)"),  # 맛 표기는 다른 메뉴로 본다
        ("돈까스", "치즈돈까스"),
        ("제육볶음", "오징어볶음"),
    ],
)
def test_match_key_keeps_different_menus_apart(a, b):
    """접는 규칙을 넓히다 서로 다른 메뉴가 합쳐지면 통계가 통째로 망가진다."""
    assert match_key(a) != match_key(b)


def test_match_key_is_stable_and_idempotent():
    once = match_key("연어 파피요트(연어:노르웨이산)")
    assert match_key(once) == once


def test_pair_likely_same_menu_finds_notation_splits():
    """매칭 진단의 두 목록에서 표기만 다른 짝을 짚어준다."""
    pairs = pair_likely_same_menu(
        plan_only=["연어 파피요트", "정말로안먹은메뉴"],
        log_only=["연어파피요트", "다른메뉴"],
    )
    assert pairs == [{"plan_name": "연어 파피요트", "log_name": "연어파피요트"}]


def test_pair_likely_same_menu_is_empty_when_nothing_matches():
    assert pair_likely_same_menu(["김치찌개"], ["부대찌개"]) == []
