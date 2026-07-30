"""주간 식단표의 주찬(메인) × 부찬 조합별 만족도 비교 + 대략적인 영양 균형 프록시.

전제(사용자 확인, 2026-07): 같은 메인메뉴는 항상 같은 부찬을 받는다 —
구내식당 특성상 그날 그 코너의 메인을 고른 사람은 다 같은 부찬을 받으므로,
"누가 부찬 A를 골랐는지"가 아니라 **날짜 단위로 부찬 조합을 비교**하면 된다.
같은 메인 메뉴가 다른 날 다른 부찬과 나왔을 때, 그 날짜의 평균 만족도를
조합별로 묶어 비교한다.
"""

import datetime as dt
import statistics
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.enums import MenuRole, TASTE_SCORE_POINTS
from app.models.logs import MealLog, WeeklyMenuPlan
from app.services.food_vector import FOOD_VECTOR_DIMENSIONS, FOOD_VECTOR_LABELS_KO


@dataclass(frozen=True)
class ComboDay:
    plan_date: dt.date
    side_menu_ids: frozenset[int]
    avg_satisfaction: float | None  # 그날 그 코너에서 main_menu_id로 찍힌 meal_log 평균


@dataclass(frozen=True)
class ComboSummary:
    side_menu_ids: frozenset[int]
    day_count: int
    avg_satisfaction: float | None


def build_side_combos_for_main_menu(
    db: Session, main_menu_id: int, period_start: dt.date, period_end: dt.date
) -> list[ComboDay]:
    """기간 내 main_menu_id가 MAIN으로 나온 (날짜, 코너, 식사구분)마다, 같은
    슬롯의 SIDE 메뉴 목록과 그날 그 코너의 main_menu_id 평균 만족도를 묶는다."""
    main_slots = (
        db.query(WeeklyMenuPlan.plan_date, WeeklyMenuPlan.corner_id, WeeklyMenuPlan.meal_type)
        .filter(
            WeeklyMenuPlan.menu_id == main_menu_id,
            WeeklyMenuPlan.menu_role == MenuRole.MAIN,
            WeeklyMenuPlan.plan_date.between(period_start, period_end),
        )
        .distinct()
        .all()
    )
    if not main_slots:
        return []

    dates = {plan_date for plan_date, _, _ in main_slots}
    corner_ids = {corner_id for _, corner_id, _ in main_slots}

    side_rows = (
        db.query(WeeklyMenuPlan.plan_date, WeeklyMenuPlan.corner_id, WeeklyMenuPlan.meal_type, WeeklyMenuPlan.menu_id)
        .filter(
            WeeklyMenuPlan.menu_role == MenuRole.SIDE,
            WeeklyMenuPlan.plan_date.in_(dates),
            WeeklyMenuPlan.corner_id.in_(corner_ids),
        )
        .all()
    )
    sides_by_slot: dict[tuple[dt.date, int, str], set[int]] = {}
    for plan_date, corner_id, meal_type, menu_id in side_rows:
        sides_by_slot.setdefault((plan_date, corner_id, meal_type), set()).add(menu_id)

    results = []
    for plan_date, corner_id, meal_type in main_slots:
        day_start = dt.datetime.combine(plan_date, dt.time())
        day_end = day_start + dt.timedelta(days=1)
        scores = (
            db.query(MealLog.taste_score)
            .filter(
                MealLog.menu_id == main_menu_id,
                MealLog.corner_id == corner_id,
                MealLog.eaten_at >= day_start,
                MealLog.eaten_at < day_end,
                MealLog.taste_score.isnot(None),
            )
            .all()
        )
        score_values = [TASTE_SCORE_POINTS[s] for (s,) in scores]
        results.append(
            ComboDay(
                plan_date=plan_date,
                side_menu_ids=frozenset(sides_by_slot.get((plan_date, corner_id, meal_type), set())),
                avg_satisfaction=statistics.fmean(score_values) if score_values else None,
            )
        )
    return results


def compute_combo_satisfaction_summary(
    days: list[ComboDay], *, min_day_count: int = 1
) -> list[ComboSummary]:
    """순수 함수 — side_menu_ids 조합별로 등장일수/평균 만족도를 묶어 만족도
    내림차순(평가 없는 조합은 맨 뒤)으로 정렬한다."""
    day_counts: dict[frozenset[int], int] = {}
    scores_by_combo: dict[frozenset[int], list[float]] = {}
    for d in days:
        day_counts[d.side_menu_ids] = day_counts.get(d.side_menu_ids, 0) + 1
        if d.avg_satisfaction is not None:
            scores_by_combo.setdefault(d.side_menu_ids, []).append(d.avg_satisfaction)

    results = [
        ComboSummary(
            side_menu_ids=combo,
            day_count=count,
            avg_satisfaction=(
                statistics.fmean(scores_by_combo[combo]) if combo in scores_by_combo else None
            ),
        )
        for combo, count in day_counts.items()
        if count >= min_day_count
    ]
    results.sort(key=lambda c: (c.avg_satisfaction is None, -(c.avg_satisfaction or 0)))
    return results


def compute_combo_nutrition_profile(
    menu_ids: list[int], food_vectors: dict[int, list[float]]
) -> dict[str, float]:
    """순수 함수 — 조합에 속한 메뉴들의 food_vector를 차원별 평균해 한글 라벨로
    돌려준다. ⚠️ 실제 칼로리/영양성분 DB가 없으므로 food_vector(매운맛/단백질/
    채소 비중 등 0~1 프록시 값)의 평균일 뿐인 "영양 균형 추정치"다 — 실측 아님."""
    vectors = [food_vectors[m] for m in menu_ids if m in food_vectors]
    if not vectors:
        return {}
    return {
        FOOD_VECTOR_LABELS_KO.get(dim, dim): round(statistics.fmean(v[i] for v in vectors), 2)
        for i, dim in enumerate(FOOD_VECTOR_DIMENSIONS)
    }
