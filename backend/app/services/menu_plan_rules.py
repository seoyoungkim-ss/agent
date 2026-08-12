"""§77(2026-08): 주간 식단표 규칙 검증 — 담당자가 준 4개 기준을 그 주(월~금)
편성 전체에 대해 판정한다. `weather_event.py`/`season.py`와 같은 순수함수
스타일 — DB 접근은 호출부(`analysis.py`)가 하고, 여기는 이미 모인 슬롯 목록만
받아 판정한다.

① 해장 메뉴 최소 1개
② 면류(라면 포함) 4개 초과 편성 금지
③ 매운(빨간국물) 메뉴 4개 초과 편성 금지
④ (여기 없음 — analysis.py가 직접 처리) 최근 식수 200식 이하 메뉴는 재편성 금지

①~③은 물리적으로 "그 주에 뭐가 나갔는지"를 보는 것이라 menu_role(메인/부찬/
건강가든) 무관하게 전부 스캔한다(§132의 "건강가든은 코너 무관" 관례와 같은
원칙). "매운(빨간국물)"은 새 키워드 목록을 또 만들기보다
`food_vector_tagging.menu_matches_dimension`의 spicy ∩ soup_based 판정을
재사용한다 — 유지보수할 키워드 목록이 하나 줄어든다.
"""

import datetime as dt
from dataclasses import dataclass

from app.services.food_vector_tagging import menu_matches_dimension

# "해장"은 food_vector 차원에 없어 새 키워드 목록이 필요하다.
_HANGOVER_KEYWORDS = ("해장", "북엇국", "황태", "콩나물국밥", "우거지", "뼈해장국", "선지해장국")

# "면류"도 없다 — food_vector의 carb 차원은 밥/떡/빵까지 포함해 너무 넓다.
_NOODLE_KEYWORDS = ("면", "국수", "라면", "우동", "짜장", "짬뽕", "파스타", "스파게티", "쌀국수", "당면", "냉면", "쫄면")


def is_hangover_dish(menu_name: str) -> bool:
    return any(kw in menu_name for kw in _HANGOVER_KEYWORDS)


def is_noodle_dish(menu_name: str) -> bool:
    return any(kw in menu_name for kw in _NOODLE_KEYWORDS)


def is_spicy_red_broth_dish(menu_name: str) -> bool:
    return menu_matches_dimension(menu_name, "spicy") and menu_matches_dimension(menu_name, "soup_based")


@dataclass(frozen=True)
class MenuPlanSlotItem:
    """규칙 검증 대상 하나 — 그 주에 편성된 메뉴 한 건."""

    menu_name: str
    corner_name: str
    plan_date: dt.date


@dataclass(frozen=True)
class MenuPlanRuleResult:
    ok: bool
    count: int
    limit: int | None  # 해장(최소 1개)은 상한이 없어 None
    matches: list[str]  # "메뉴명(코너, 7/21)" 라벨


def _label(item: MenuPlanSlotItem) -> str:
    return f"{item.menu_name}({item.corner_name}, {item.plan_date.month}/{item.plan_date.day})"


def check_hangover_rule(slots: list[MenuPlanSlotItem]) -> MenuPlanRuleResult:
    matched = [s for s in slots if is_hangover_dish(s.menu_name)]
    return MenuPlanRuleResult(ok=len(matched) >= 1, count=len(matched), limit=None, matches=[_label(s) for s in matched])


def check_noodle_rule(slots: list[MenuPlanSlotItem], limit: int = 4) -> MenuPlanRuleResult:
    matched = [s for s in slots if is_noodle_dish(s.menu_name)]
    return MenuPlanRuleResult(ok=len(matched) <= limit, count=len(matched), limit=limit, matches=[_label(s) for s in matched])


def check_spicy_red_broth_rule(slots: list[MenuPlanSlotItem], limit: int = 4) -> MenuPlanRuleResult:
    matched = [s for s in slots if is_spicy_red_broth_dish(s.menu_name)]
    return MenuPlanRuleResult(ok=len(matched) <= limit, count=len(matched), limit=limit, matches=[_label(s) for s in matched])
