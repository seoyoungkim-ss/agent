"""PRD 6.2: 코너별 코어층 분석 (해당 코너를 반복적으로 선택하는 사번 그룹).

방문 횟수만 보면 "여기저기 다 자주 가는 헤비유저"가 모든 코너의 코어층으로 잘못
잡히고, 비중만 보면 표본이 아주 적은 사람(1번 방문해서 그게 100%)이 섞여 들어온다
— 그래서 두 조건을 AND로 함께 요구한다.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.enums import MenuRole
from app.models.logs import MealLog, WeeklyMenuPlan


@dataclass(frozen=True)
class CoreLayerResult:
    employee_id: str
    corner_visit_count: int
    total_visit_count: int
    corner_share: float


def classify_corner_core_layer(
    employee_corner_counts: dict[str, dict[int, int]],
    corner_id: int,
    *,
    min_visit_count: int = 3,
    min_share: float = 0.3,
) -> list[CoreLayerResult]:
    """순수 함수 — employee_corner_counts는 {사번: {corner_id: 방문횟수}}."""
    results = []
    for emp, counts in employee_corner_counts.items():
        corner_count = counts.get(corner_id, 0)
        if corner_count < min_visit_count:
            continue
        total = sum(counts.values())
        if total == 0:
            continue
        share = corner_count / total
        if share < min_share:
            continue
        results.append(CoreLayerResult(emp, corner_count, total, share))
    results.sort(key=lambda r: (r.corner_share, r.corner_visit_count), reverse=True)
    return results


def build_employee_corner_counts(
    db: Session, period_start: dt.date, period_end: dt.date
) -> dict[str, dict[int, int]]:
    """meal_log에서 기간 내 사번별 코너별 방문 횟수를 센다.

    기간 필터는 menu_affinity.py::build_employee_menu_sets와 동일한
    [period_start, period_end+1일 배타적상한] 패턴(레포 전역 컨벤션).
    """
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    period_start_dt = dt.datetime.combine(period_start, dt.time())
    rows = (
        db.query(MealLog.employee_id, MealLog.corner_id)
        .filter(MealLog.eaten_at >= period_start_dt, MealLog.eaten_at < period_end_exclusive)
        .all()
    )
    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for employee_id, corner_id in rows:
        counts[employee_id][corner_id] += 1
    return {emp: dict(c) for emp, c in counts.items()}


@dataclass(frozen=True)
class MenuControlledCornerPreference:
    corner_id: int
    contested_occasions: int  # 이 코너가 낀 "동일 메뉴 여러 코너 동시 제공" 상황의 전체 참여자 수 합
    chosen_count: int  # 그 상황들에서 실제로 이 코너를 고른 인원 수 합
    preference_ratio: float  # chosen_count / contested_occasions


def classify_menu_controlled_corner_preference(
    contested_rows: list[tuple[dt.date, int, int]],
) -> dict[int, MenuControlledCornerPreference]:
    """순수 함수 — (날짜, 메뉴id, 코너id) 목록(이미 "같은 날 같은 메인메뉴가 2개
    이상 코너에서 동시 제공된" 경우만 걸러진 meal_log 행)에서, 코너별로 "메뉴가
    같아도 실제로 이 코너를 고른 비율"을 계산한다.

    메뉴가 동일하니 코너 선택은 순수하게 코너 선호를 반영한다고 볼 수 있다는
    아이디어(PRD, 2026-07) — 방문 빈도/비중(classify_corner_core_layer)과는
    다른 신호라 AND로 합치지 않고 별도 지표로 나란히 보여준다.
    """
    group_totals: dict[tuple[dt.date, int], int] = defaultdict(int)  # (날짜,메뉴id) -> 전체 참여자 수
    corner_group_counts: dict[tuple[dt.date, int, int], int] = defaultdict(int)  # (날짜,메뉴id,코너id) -> 인원
    for plan_date, menu_id, corner_id in contested_rows:
        group_totals[(plan_date, menu_id)] += 1
        corner_group_counts[(plan_date, menu_id, corner_id)] += 1

    corner_chosen: dict[int, int] = defaultdict(int)
    corner_total: dict[int, int] = defaultdict(int)
    for (plan_date, menu_id, corner_id), chosen in corner_group_counts.items():
        corner_chosen[corner_id] += chosen
        corner_total[corner_id] += group_totals[(plan_date, menu_id)]

    return {
        corner_id: MenuControlledCornerPreference(
            corner_id=corner_id,
            contested_occasions=corner_total[corner_id],
            chosen_count=corner_chosen[corner_id],
            preference_ratio=corner_chosen[corner_id] / corner_total[corner_id] if corner_total[corner_id] else 0.0,
        )
        for corner_id in corner_chosen
    }


def build_menu_controlled_meal_log_rows(
    db: Session, period_start: dt.date, period_end: dt.date
) -> list[tuple[dt.date, int, int]]:
    """같은 날 같은 메인메뉴(menu_id)가 2개 이상 코너에서 동시 제공된 경우만 골라,
    그 상황에서 실제 취식된 (날짜, 메뉴id, 코너id) 행을 돌려준다 —
    classify_menu_controlled_corner_preference의 입력.
    """
    plan_rows = (
        db.query(WeeklyMenuPlan.plan_date, WeeklyMenuPlan.menu_id, WeeklyMenuPlan.corner_id)
        .filter(
            WeeklyMenuPlan.plan_date >= period_start,
            WeeklyMenuPlan.plan_date <= period_end,
            WeeklyMenuPlan.menu_role == MenuRole.MAIN,
        )
        .all()
    )
    corners_by_date_menu: dict[tuple[dt.date, int], set[int]] = defaultdict(set)
    for plan_date, menu_id, corner_id in plan_rows:
        corners_by_date_menu[(plan_date, menu_id)].add(corner_id)
    contested_date_menus = {k for k, corners in corners_by_date_menu.items() if len(corners) >= 2}
    if not contested_date_menus:
        return []

    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    period_start_dt = dt.datetime.combine(period_start, dt.time())
    meal_rows = (
        db.query(MealLog.eaten_at, MealLog.corner_id, MealLog.menu_id)
        .filter(
            MealLog.eaten_at >= period_start_dt,
            MealLog.eaten_at < period_end_exclusive,
            MealLog.menu_id.isnot(None),
        )
        .all()
    )
    return [
        (eaten_at.date(), menu_id, corner_id)
        for eaten_at, corner_id, menu_id in meal_rows
        if (eaten_at.date(), menu_id) in contested_date_menus
    ]
