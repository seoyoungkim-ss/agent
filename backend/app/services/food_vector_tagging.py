"""PRD 6.1: 메뉴명 → food_vector(10차원) 자동 태깅.

실측 데이터가 메뉴명(문자열)만 주므로 3단계로 채운다:
1. 신메뉴가 처음 인입될 때(`master_data.get_or_create_menu`) 키워드 규칙으로 즉시
   태깅한다(`tag_food_vector_from_name`). 매칭되는 키워드가 하나도 없으면
   food_vector를 비워둔 채(NULL) 다음 단계로 넘긴다.
2. 관리자가 `POST /api/analysis/menus/tag-with-llm`을 호출하면 규칙으로 못 잡은
   (food_vector IS NULL) 메뉴만 골라 사내 LLM에게 태깅을 요청한다(`run_llm_food_vector_tagging`).
3. 관리자가 `PUT /api/analysis/menus/{menu_id}/food-vector`로 언제든 수동 조정할 수
   있고, 이 경우 source=MANUAL로 표시되어 이후 1·2단계 배치가 건드리지 않는다
   (두 배치 모두 food_vector IS NULL인 메뉴만 대상으로 하므로 자동으로 보호됨).
"""

from sqlalchemy.orm import Session

from app.models.enums import FoodVectorSource
from app.models.master import MenuMaster
from app.services.food_vector import FOOD_VECTOR_DIMENSIONS
from app.services.menu_name import strip_origin_annotation
from app.services.llm_client import InternalLLMClient

# 규칙에 걸리면 이 값, 안 걸리면 이 값 — 둘 다 0~1 스케일(food_vector.py 컨벤션).
_MATCH_SCORE = 0.85
_DEFAULT_SCORE = 0.2

# 메뉴명에 이 키워드 중 하나라도 포함되면 해당 차원을 "그러하다"로 태깅한다.
# 여러 메뉴에 걸쳐 반복 등장하는 흔한 한식 조리법/재료 위주로 구성한 1차 규칙표이며,
# 실제 태깅 결과를 보며 계속 보강해야 한다(수정은 이 딕셔너리만 고치면 됨).
_KEYWORD_RULES: dict[str, tuple[str, ...]] = {
    "spicy": ("매운", "매콤", "불닭", "낙지", "짬뽕", "김치", "고추", "마라", "얼큰", "화끈"),
    "sweet": ("탕수육", "케첩", "잼", "글레이즈", "단짠", "고구마", "완자"),
    "salty": ("젓갈", "장아찌", "간장", "된장", "젓", "짠지"),
    "sour": ("새콤", "식초", "레몬", "냉면", "비빔"),
    "oily": ("튀김", "볶음", "부침", "전", "돈까스", "탕수육", "기름"),
    "protein": ("고기", "돈까스", "치킨", "제육", "불고기", "삼겹살", "생선", "계란", "두부", "스테이크", "함박"),
    "carb": ("면", "국수", "라면", "밥", "떡", "빵", "우동", "짜장", "파스타"),
    "fried": ("튀김", "돈까스", "까스", "프라이", "탕수육"),
    # "국"을 그대로 두면 "외국산"·"중국산"·"국내산"에 전부 걸린다(2026-08 실사용
    # 신고). 그 여파가 단순 오태깅에서 끝나지 않는 게 문제였다 — 규칙이 하나라도
    # 걸리면 food_vector가 NULL이 아니게 채워지고, LLM 보정 배치는
    # `food_vector IS NULL`만 대상으로 하므로 그 행이 **영구히 보정 대상에서
    # 빠진다**(3단계 안전망의 2단계 무력화). 국물 메뉴는 "국"이 이름 끝에 오므로
    # 접미어로 좁히고, 나머지는 더 구체적인 키워드로 잡는다.
    "soup_based": ("국물", "탕", "찌개", "국밥", "스프", "우동", "전골", "샤브"),
    "vegetable_ratio": ("나물", "샐러드", "채소", "야채", "무침", "쌈", "비빔"),
}


# "미역국"·"된장국"처럼 이름이 "국"으로 끝나는 국물 메뉴. 접미어로만 인정해
# "중국산"·"외국산"이 걸리지 않게 한다.
_SOUP_SUFFIX = "국"


def tag_food_vector_from_name(menu_name: str) -> tuple[list[float], bool]:
    """returns (vector, matched_any).

    matched_any=False면 어떤 규칙도 안 걸렸다는 뜻 — 호출부는 이 경우 food_vector를
    채우지 말고(NULL 유지) LLM/수동 태깅을 기다려야 한다.
    """
    # 원산지 주석이 이름에 남아 있어도 태깅을 오염시키지 않도록 먼저 떼어낸다.
    menu_name = strip_origin_annotation(menu_name)
    vector: list[float] = []
    matched_any = False
    for dim in FOOD_VECTOR_DIMENSIONS:
        matched = any(kw in menu_name for kw in _KEYWORD_RULES.get(dim, ()))
        if dim == "soup_based" and not matched:
            matched = menu_name.endswith(_SOUP_SUFFIX)
        if matched:
            vector.append(_MATCH_SCORE)
            matched_any = True
        else:
            vector.append(_DEFAULT_SCORE)
    return vector, matched_any


def _parse_llm_vector_response(response: str) -> list[float] | None:
    """'spicy: 0.8, sweet: 0.1, ...' 형식 응답을 파싱한다. 차원이 하나라도 빠지거나
    형식이 깨지면 None(이번 태깅은 실패로 간주하고 다음 배치에서 재시도)."""
    values: dict[str, float] = {}
    for part in response.replace("\n", ",").split(","):
        if ":" not in part:
            continue
        key, _, raw_value = part.partition(":")
        key = key.strip().lower()
        if key not in FOOD_VECTOR_DIMENSIONS:
            continue
        try:
            values[key] = max(0.0, min(1.0, float(raw_value.strip())))
        except ValueError:
            continue
    if len(values) != len(FOOD_VECTOR_DIMENSIONS):
        return None
    return [values[dim] for dim in FOOD_VECTOR_DIMENSIONS]


async def tag_food_vector_via_llm(llm_client: InternalLLMClient, menu_name: str) -> list[float] | None:
    dims = ", ".join(FOOD_VECTOR_DIMENSIONS)
    prompt = (
        f"다음 한식 구내식당 메뉴 '{menu_name}'의 특성을 아래 {len(FOOD_VECTOR_DIMENSIONS)}개 "
        f"항목에 대해 0.0(전혀 아님)~1.0(매우 그러함) 사이 숫자로 평가하세요. 항목: {dims}. "
        "다른 설명 없이 'spicy: 0.8, sweet: 0.1, ...' 형식으로만 답하세요."
    )
    response = await llm_client.chat_complete([{"role": "user", "content": prompt}])
    return _parse_llm_vector_response(response)


async def run_llm_food_vector_tagging(db: Session, llm_client: InternalLLMClient) -> int:
    """규칙 기반으로 못 잡은(food_vector IS NULL) 메뉴만 대상으로 LLM 태깅을 보강한다."""
    untagged = db.query(MenuMaster).filter(MenuMaster.food_vector.is_(None)).all()
    tagged = 0
    for menu in untagged:
        vector = await tag_food_vector_via_llm(llm_client, menu.menu_name)
        if vector is None:
            continue
        menu.food_vector = vector
        menu.food_vector_source = FoodVectorSource.LLM
        tagged += 1
    db.commit()
    return tagged
