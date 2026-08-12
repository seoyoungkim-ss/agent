"""§77~§78(2026-08): 주간 식단표 규칙 검증 — 담당자가 준 4개 기준을 판정한다.
`weather_event.py`/`season.py`와 같은 순수함수 스타일 — DB 접근은 호출부
(`analysis.py`)가 하고, 여기는 이미 모인 슬롯 목록만 받아 판정한다.

① 해장 메뉴 최소 1개
② 면류(라면 포함) 4개 초과 편성 금지
③ 매운(빨간국물) 메뉴 4개 초과 편성 금지
④ (여기 없음 — analysis.py가 직접 처리) 최근 식수 200식 이하 메뉴는 재편성 금지

§78: ①~③은 **한 주 전체 합산이 아니라 요일별(하루 기준)**로 판정한다(담당자
피드백 — "하루에 면류 4개 초과 금지 이런 식") — 토/일은 대상에서 뺀다("주중
만"). §77에서는 기간 전체 슬롯을 한 번에 세는 방식이었는데, 그러면 "이번 주에
라면 5번 나왔다"는 식으로만 보여 실제 하루 편성 밀도를 못 잡았다. 이제 날짜별로
묶어 그날 하루의 매치 개수만 본다 — "해장 최소 1개"도 하루 기준으로 재해석해
그날 슬롯 중 해장 메뉴가 0개면 그날이 위반이다. 슬롯 자체가 아예 없는 날(식단표
미등록)은 판정 대상에서 빠진다 — 데이터 누락과 "편성했는데 기준 미달"은 다른
문제라 섞지 않는다.

①~③은 물리적으로 "그 날 뭐가 나갔는지"를 보는 것이라 menu_role(메인/부찬/
건강가든) 무관하게 전부 스캔한다(§132의 "건강가든은 코너 무관" 관례와 같은
원칙). "매운(빨간국물)"은 새 키워드 목록을 또 만들기보다
`food_vector_tagging.menu_matches_dimension`의 spicy ∩ soup_based 판정을
재사용한다 — 유지보수할 키워드 목록이 하나 줄어든다.
"""

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

from app.services.food_vector_tagging import menu_matches_dimension

# "해장"은 food_vector 차원에 없어 새 키워드 목록이 필요하다.
_HANGOVER_KEYWORDS = ("해장", "북엇국", "황태", "콩나물국밥", "우거지", "뼈해장국", "선지해장국")

# "면류"도 없다 — food_vector의 carb 차원은 밥/떡/빵까지 포함해 너무 넓다.
_NOODLE_KEYWORDS = ("면", "국수", "라면", "우동", "짜장", "짬뽕", "파스타", "스파게티", "쌀국수", "당면", "냉면", "쫄면")

# 요일 인덱스(월=0 ... 일=6) 기준 — 이 값 이상이면 주말(토=5, 일=6).
_SATURDAY = 5


def is_hangover_dish(menu_name: str) -> bool:
    return any(kw in menu_name for kw in _HANGOVER_KEYWORDS)


def is_noodle_dish(menu_name: str) -> bool:
    return any(kw in menu_name for kw in _NOODLE_KEYWORDS)


def is_spicy_red_broth_dish(menu_name: str) -> bool:
    return menu_matches_dimension(menu_name, "spicy") and menu_matches_dimension(menu_name, "soup_based")


@dataclass(frozen=True)
class MenuPlanSlotItem:
    """규칙 검증 대상 하나 — 그 주에 편성된 메뉴 한 건.

    corner_id는 프론트가 주간 식단표 격자표의 셀 키(`${plan_date}_${corner_id}`,
    `AnalysisPage.tsx`)를 그대로 만들어 위반 메뉴 클릭 시 해당 셀을 하이라이트할
    수 있게 하려고 둔다(§78).
    """

    menu_name: str
    corner_id: int
    corner_name: str
    plan_date: dt.date


@dataclass(frozen=True)
class MenuPlanRuleMatch:
    menu_name: str
    corner_id: int
    corner_name: str
    plan_date: dt.date


@dataclass(frozen=True)
class DailyRuleResult:
    plan_date: dt.date
    ok: bool
    count: int
    limit: int | None  # 해장(최소 1개)은 상한이 없어 None
    matches: list[MenuPlanRuleMatch]


def _match(item: MenuPlanSlotItem) -> MenuPlanRuleMatch:
    return MenuPlanRuleMatch(
        menu_name=item.menu_name,
        corner_id=item.corner_id,
        corner_name=item.corner_name,
        plan_date=item.plan_date,
    )


def _check_daily(
    slots: list[MenuPlanSlotItem],
    predicate: Callable[[str], bool],
    *,
    limit: int | None = None,
    min_count: int = 0,
) -> list[DailyRuleResult]:
    """주중(월~금)에 한해 날짜별로 묶어 그날 하루의 매치 개수만 판정한다.

    limit이 주어지면 "그 이하여야 통과"(면류/매운빨간국물), None이면 min_count
    이상이어야 통과(해장 최소 1개)로 해석한다.
    """
    by_date: dict[dt.date, list[MenuPlanSlotItem]] = {}
    for s in slots:
        if s.plan_date.weekday() >= _SATURDAY:  # 주중만 — 토/일 제외
            continue
        by_date.setdefault(s.plan_date, []).append(s)

    results = []
    for plan_date in sorted(by_date):
        matched = [s for s in by_date[plan_date] if predicate(s.menu_name)]
        count = len(matched)
        ok = count >= min_count if limit is None else count <= limit
        results.append(DailyRuleResult(plan_date=plan_date, ok=ok, count=count, limit=limit, matches=[_match(s) for s in matched]))
    return results


def check_hangover_rule(slots: list[MenuPlanSlotItem]) -> list[DailyRuleResult]:
    return _check_daily(slots, is_hangover_dish, limit=None, min_count=1)


def check_noodle_rule(slots: list[MenuPlanSlotItem], limit: int = 4) -> list[DailyRuleResult]:
    return _check_daily(slots, is_noodle_dish, limit=limit)


def check_spicy_red_broth_rule(slots: list[MenuPlanSlotItem], limit: int = 4) -> list[DailyRuleResult]:
    return _check_daily(slots, is_spicy_red_broth_dish, limit=limit)
