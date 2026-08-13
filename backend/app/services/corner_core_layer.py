"""PRD 6.2: 코너별 코어층 분석 (해당 코너를 반복적으로 선택하는 사번 그룹).

방문 횟수만 보면 "여기저기 다 자주 가는 헤비유저"가 모든 코너의 코어층으로 잘못
잡히고, 비중만 보면 표본이 아주 적은 사람(1번 방문해서 그게 100%)이 섞여 들어온다
— 그래서 두 조건을 AND로 함께 요구한다.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.logs import MealLog


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
    db: Session, period_start: dt.date, period_end: dt.date, *, exclude_corner_ids: set[int] | None = None
) -> dict[str, dict[int, int]]:
    """meal_log에서 기간 내 사번별 코너별 방문 횟수를 센다.

    기간 필터는 menu_affinity.py::build_employee_menu_sets와 동일한
    [period_start, period_end+1일 배타적상한] 패턴(레포 전역 컨벤션).

    exclude_corner_ids로 제외한 코너는 그 코너 자체의 카운트뿐 아니라
    total(분모)에도 안 잡히게 한다 — 안 그러면 그 코너를 뺀 요약 표에서도
    다른 코너들의 corner_share가 실제보다 낮게 나온다(2026-08, 코어층
    분석에서 Take Out 제외).
    """
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    period_start_dt = dt.datetime.combine(period_start, dt.time())
    query = db.query(MealLog.employee_id, MealLog.corner_id).filter(
        MealLog.eaten_at >= period_start_dt, MealLog.eaten_at < period_end_exclusive
    )
    if exclude_corner_ids:
        query = query.filter(MealLog.corner_id.notin_(exclude_corner_ids))
    counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for employee_id, corner_id in query.all():
        counts[employee_id][corner_id] += 1
    return {emp: dict(c) for emp, c in counts.items()}
