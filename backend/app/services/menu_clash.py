"""한 끼 구성(슬롯) 안에서 메인·부찬·건강가든이 서로 겹치는지 진단한다 (2026-08).

담당자 요청: "같은 메뉴 안에서 부찬과 주찬의 재료가 중복되거나 혹은 부찬끼리
재료 또는 카테고리 중복을 보고싶다."

    콩나물국밥(메인) + 콩나물무침(부찬)   → 재료 중복
    순두부찌개(메인) + 매운양념 부찬       → 맛 중복
    메인이 탄수화물 위주 + 부찬도 탄수화물 → 영양 카테고리 중복

**`menu_rotation.py`와 축이 다르다.** 저쪽은 "이 메뉴 최근에 또 내보내지
않았나"(기간 내 같은 메뉴 반복), 이쪽은 "이 한 끼 구성이 겹치지 않나"(슬롯 내
서로 다른 메뉴끼리의 재료·특성 겹침). 둘 다 필요하다.

이 모듈은 DB를 모른다 — 메뉴명 문자열과 food_vector 값만 받는 순수 함수라
테스트가 쉽다. DB 조회는 `app/api/analysis.py`의 엔드포인트가 맡는다(레포 관례).
"""

from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

from app.services.food_vector import FOOD_VECTOR_DIMENSIONS, FOOD_VECTOR_LABELS_KO

# ---------------------------------------------------------------------------
# 재료 중복
# ---------------------------------------------------------------------------
# food_vector_tagging._KEYWORD_RULES는 "차원"(매운맛/탄수화물...) 키워드지
# 식재료 사전이 아니다 — "콩나물"이 거기 없다. 그래서 별도로 둔다.
#
# ⚠️ 1차 규칙표다. 여기 없는 재료는 못 잡는다(_KEYWORD_RULES도 같은 성격으로
# "실제 결과를 보며 계속 보강해야 한다"고 적혀 있다). 이 레포의 3단계 패턴
# (규칙 → LLM → 수동)에서 1단계만 한 셈이고, 커버리지가 부족하면 LLM 재료
# 추출을 붙이는 게 다음 단계다.
#
# 전부 2자 이상이다 — "무" 같은 1자 토큰을 넣으면 "무침"·"무국"·"무말랭이"에
# 전부 걸려 오탐이 난다. 1자 재료는 이 방식으론 다룰 수 없다고 보고 뺀다.
_INGREDIENT_TOKENS: tuple[str, ...] = (
    # 채소·나물류
    "콩나물", "숙주", "시금치", "고사리", "도라지", "취나물", "미나리", "부추",
    "배추", "양배추", "오이", "가지", "호박", "당근", "양파", "대파", "브로콜리",
    "파프리카", "토마토", "감자", "고구마", "연근", "우엉", "무말랭이",
    # 버섯·해조류
    "버섯", "느타리", "팽이", "표고", "미역", "다시마", "파래",
    # 단백질
    "두부", "순두부", "계란", "달걀", "메추리알", "돼지고기", "소고기", "닭고기",
    "오리고기", "제육", "삼겹살", "목살", "차돌", "베이컨", "햄", "소시지",
    "어묵", "오징어", "낙지", "새우", "고등어", "삼치", "갈치", "코다리", "명태",
    "참치", "꽁치", "동태", "황태", "쭈꾸미", "홍합", "바지락",
    # 기타
    "김치", "된장", "고추장", "카레", "치즈", "떡", "당면", "김밥",
)
# 위 목록에 실수로 섞인 비한글/1자 토큰을 방어적으로 걸러낸다 — 사전을 손으로
# 늘려가는 구조라 오타가 그대로 오탐이 되는 걸 막는다.
_INGREDIENT_TOKENS = tuple(
    t for t in _INGREDIENT_TOKENS if len(t) >= 2 and all("가" <= ch <= "힣" for ch in t)
)


def extract_ingredients(menu_name: str, stored: Sequence[str] | None = None) -> set[str]:
    """메뉴의 식재료 집합.

    `stored`(menu_master.ingredients)가 있으면 그걸 쓴다 — 규칙 사전이 못 잡는
    재료를 LLM이 채워 넣은 결과다(2026-08). 없으면 이름 기반 규칙으로 폴백한다.
    이게 이 레포의 3단계 패턴(규칙 → LLM → 수동)에서 조회 쪽 진입점이다.

    "콩나물국밥" → {"콩나물"}, "돼지고기김치찌개" → {"돼지고기", "김치"}.
    """
    if stored:
        return {t.strip() for t in stored if t and t.strip()}
    return extract_ingredients_from_name(menu_name)


def extract_ingredients_from_name(menu_name: str) -> set[str]:
    """규칙 사전 기반 추출(3단계의 1단계). 사전에 없는 재료는 안 잡힌다."""
    return {token for token in _INGREDIENT_TOKENS if token in menu_name}


@dataclass(frozen=True)
class IngredientClash:
    menu_a: str
    menu_b: str
    shared: list[str]  # 두 메뉴가 공유하는 재료(정렬됨)


def find_ingredient_clashes(
    main_name: str | None,
    side_names: Sequence[str],
    *,
    ingredients_by_name: dict[str, Sequence[str]] | None = None,
) -> list[IngredientClash]:
    """메인↔부찬, 부찬↔부찬 모든 쌍에서 공유 재료를 찾는다.

    부찬끼리도 보는 이유: 요청이 "부찬과 주찬" 뿐 아니라 "부찬끼리 재료 또는
    카테고리 중복"도 포함했다.
    """
    stored = ingredients_by_name or {}
    named = [(name, extract_ingredients(name, stored.get(name))) for name in side_names]
    if main_name is not None:
        # 메인을 맨 앞에 둬서 메인↔부찬 쌍이 결과 앞쪽에 오게 한다.
        named.insert(0, (main_name, extract_ingredients(main_name, stored.get(main_name))))

    clashes = []
    for (name_a, ing_a), (name_b, ing_b) in combinations(named, 2):
        shared = ing_a & ing_b
        if shared:
            clashes.append(
                IngredientClash(menu_a=name_a, menu_b=name_b, shared=sorted(shared))
            )
    return clashes


# ---------------------------------------------------------------------------
# 특성(카테고리) 중복 — food_vector 재사용
# ---------------------------------------------------------------------------
# 겹치면 문제가 되는 차원만 본다. protein(단백질)과 vegetable_ratio(채소)를 뺀
# 이유: 단백질이 겹치거나 채소가 겹치는 건 문제가 아니라 오히려 좋다. 겹쳐서
# 물리거나 영양이 한쪽으로 쏠리는 차원만 대상으로 한다.
# sweet/sour는 겹쳐도 문제인지 판단이 애매해 v0에선 뺐다 — 피드백 후 추가한다.
_CLASH_DIMENSIONS: tuple[str, ...] = ("spicy", "carb", "fried", "oily", "soup_based", "salty")

# 규칙 태깅(food_vector_tagging)은 0.85(매칭)/0.2(미매칭) 이분법이라 사실상
# boolean이고, LLM 태깅 메뉴는 연속값이다. 0.6이면 양쪽을 같은 기준으로 다룬다.
_CLASH_THRESHOLD = 0.6


@dataclass(frozen=True)
class VectorClash:
    menu_a: str
    menu_b: str
    dimension: str  # 영문 차원명 (spicy, carb, ...)
    label_ko: str  # 화면 표기용 한글 (매운맛, 탄수화물, ...)
    value_a: float
    value_b: float


def find_vector_clashes(
    main: tuple[str, list[float] | None] | None,
    sides: Sequence[tuple[str, list[float] | None]],
    *,
    threshold: float = _CLASH_THRESHOLD,
    dimensions: Sequence[str] = _CLASH_DIMENSIONS,
) -> tuple[list[VectorClash], list[str]]:
    """returns (clashes, untagged_menu_names).

    food_vector가 None인 메뉴는 판정에서 빼고 이름을 따로 돌려준다 — 조용히
    "충돌 없음"으로 넘기면 태깅이 안 됐을 뿐인데 구성이 괜찮다고 오해한다.
    """
    entries = list(sides)
    if main is not None:
        entries.insert(0, main)

    untagged = [name for name, vec in entries if vec is None]
    tagged = [(name, vec) for name, vec in entries if vec is not None]

    dim_index = {dim: i for i, dim in enumerate(FOOD_VECTOR_DIMENSIONS)}
    clashes = []
    for (name_a, vec_a), (name_b, vec_b) in combinations(tagged, 2):
        for dim in dimensions:
            i = dim_index.get(dim)
            if i is None or i >= len(vec_a) or i >= len(vec_b):
                continue
            if vec_a[i] >= threshold and vec_b[i] >= threshold:
                clashes.append(
                    VectorClash(
                        menu_a=name_a,
                        menu_b=name_b,
                        dimension=dim,
                        label_ko=FOOD_VECTOR_LABELS_KO.get(dim, dim),
                        value_a=round(vec_a[i], 2),
                        value_b=round(vec_b[i], 2),
                    )
                )
    return clashes, untagged
