"""PRD 6.1: 메뉴 동반 선택 경향성 ("떡볶이 먹는 사람은 짜장면도 잘 먹는다").

취향 벡터 군집(taste_clustering.py)이 "이 사람의 식성이 대략 어떤 타입인가"를
요약한다면, 이 모듈은 좀 더 직접적으로 "메뉴 A를 고르는 사람이 메뉴 B도 유난히
자주 고르는가"를 계산한다. 장바구니 분석(market-basket analysis)의 lift 지표를
그대로 쓴다.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from sqlalchemy.orm import Session

from app.models.logs import MealLog
from app.models.master import MenuMaster
from app.services.master_data import PLACEHOLDER_MENU_NAMES
from app.services.taste_profile import cosine_similarity

# food_vector 코사인 유사도가 이 값 이상이면 "자명한 조합"(같은 음식 카테고리끼리,
# 예: 부대찌개+참치김치찌개)으로 본다 — 사용자가 원한 건 이런 뻔한 조합 말고
# "부대찌개를 선호하는 사람이 떡볶이도 유의미하게 선호한다" 같은 직관적이지
# 않은 연관관계라, 화면에서 이 조합들을 하단/별도로 뺄 수 있게 플래그만 계산한다.
OBVIOUS_PAIR_SIMILARITY_THRESHOLD = 0.85


def is_obvious_pair(
    vector_a: list[float] | None,
    vector_b: list[float] | None,
    *,
    threshold: float = OBVIOUS_PAIR_SIMILARITY_THRESHOLD,
) -> bool | None:
    """순수 함수 — 두 메뉴의 food_vector가 비슷할수록(같은 카테고리) 자명한
    조합으로 본다. 둘 중 하나라도 벡터가 없으면 판단 불가(None)."""
    if vector_a is None or vector_b is None:
        return None
    return cosine_similarity(vector_a, vector_b) >= threshold


@dataclass(frozen=True)
class MenuAffinityResult:
    menu_name: str
    co_count: int  # 두 메뉴를 모두 먹은 사번 수
    lift: float  # (동반 비율) / (각자 비율의 곱) — 1보다 크면 "같이 잘 나옴"


@dataclass(frozen=True)
class MenuPairResult:
    menu_a: str
    menu_b: str
    co_count: int
    lift: float


def compute_menu_affinity(
    employee_menus: dict[str, set[str]],
    target_menu: str,
    *,
    min_co_count: int = 3,
    top_n: int = 10,
) -> list[MenuAffinityResult]:
    """순수 함수 — employee_menus는 {사번: 그 사람이 먹어본 메뉴명 집합}.

    lift(A, B) = P(A,B) / (P(A) * P(B))
               = co_count * total / (count_A * count_B)
    표본이 아주 작은 메뉴 쌍(co_count < min_co_count)은 우연일 가능성이 커서 제외한다.
    """
    total = len(employee_menus)
    if total == 0:
        return []

    employees_with_target = {emp for emp, menus in employee_menus.items() if target_menu in menus}
    count_target = len(employees_with_target)
    if count_target == 0:
        return []

    co_counts: dict[str, int] = defaultdict(int)
    menu_counts: dict[str, int] = defaultdict(int)
    for menus in employee_menus.values():
        for menu in menus:
            menu_counts[menu] += 1
    for emp in employees_with_target:
        for menu in employee_menus[emp]:
            if menu != target_menu:
                co_counts[menu] += 1

    results = []
    for menu, co_count in co_counts.items():
        if co_count < min_co_count:
            continue
        count_other = menu_counts[menu]
        lift = (co_count * total) / (count_target * count_other)
        results.append(MenuAffinityResult(menu_name=menu, co_count=co_count, lift=lift))

    results.sort(key=lambda r: r.lift, reverse=True)
    return results[:top_n]


def compute_top_menu_pairs(
    employee_menus: dict[str, set[str]],
    *,
    min_co_count: int = 2,
    top_n: int = 10,
) -> list[MenuPairResult]:
    """순수 함수 — 대상 메뉴를 고정하지 않고 가장 흔한 메뉴 쌍 top_n을 뽑는다.

    1차 정렬은 co_count(가장 흔한 조합) 내림차순, 2차는 lift(참고용 연관 강도) —
    compute_menu_affinity가 lift를 1차 정렬 기준으로 쓰는 것과 의도적으로 다르다.
    min_co_count 기본값도 3이 아닌 2인데, 이 함수는 코어층처럼 표본이 작은
    부분집합에서 자주 호출될 것이라 3으로 두면 결과가 자주 비기 때문.
    """
    total = len(employee_menus)
    if total == 0:
        return []

    menu_counts: dict[str, int] = defaultdict(int)
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for menus in employee_menus.values():
        for menu in menus:
            menu_counts[menu] += 1
        for a, b in combinations(sorted(menus), 2):
            pair_counts[(a, b)] += 1

    results = []
    for (a, b), co_count in pair_counts.items():
        if co_count < min_co_count:
            continue
        lift = (co_count * total) / (menu_counts[a] * menu_counts[b])
        results.append(MenuPairResult(menu_a=a, menu_b=b, co_count=co_count, lift=lift))

    results.sort(key=lambda r: (r.co_count, r.lift), reverse=True)
    return results[:top_n]


def build_employee_menu_sets(
    db: Session, period_start: dt.date, period_end: dt.date
) -> dict[str, set[str]]:
    """meal_log에서 기간 내 사번별로 먹어본 메뉴명 집합을 만든다(빈도는 무시, 존재 여부만).

    테이크아웃 플레이스홀더 메뉴(`PLACEHOLDER_MENU_NAMES`)는 세부 메뉴를 정확히
    못 남겨 "동반 선택" 의미가 없으므로 제외한다 — 4분면 집계(aggregation.py)와
    같은 목록을 공유한다(2026-07: 이 제외가 빠져있어 코너별 분석의 메뉴 쌍에
    "선택형 Take out"이 계속 나오던 문제를 여기서 잡음).
    """
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    period_start_dt = dt.datetime.combine(period_start, dt.time())

    rows = (
        db.query(MealLog.employee_id, MealLog.menu_id)
        .filter(
            MealLog.eaten_at >= period_start_dt,
            MealLog.eaten_at < period_end_exclusive,
            MealLog.menu_id.isnot(None),
        )
        .all()
    )
    menu_names = dict(db.query(MenuMaster.menu_id, MenuMaster.menu_name).all())

    employee_menus: dict[str, set[str]] = defaultdict(set)
    for employee_id, menu_id in rows:
        name = menu_names.get(menu_id)
        if name and name not in PLACEHOLDER_MENU_NAMES:
            employee_menus[employee_id].add(name)
    return dict(employee_menus)
