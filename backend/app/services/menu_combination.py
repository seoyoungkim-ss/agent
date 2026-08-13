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
    headcount: int  # 그날 그 코너의 main_menu_id 취식 건수(식수) — 평가 여부 무관, 전부 카운트


@dataclass(frozen=True)
class ComboSummary:
    side_menu_ids: frozenset[int]
    day_count: int
    avg_satisfaction: float | None
    avg_headcount: float  # 이 조합이 등장한 날들의 평균 식수


def build_side_combos_for_main_menu(
    db: Session,
    main_menu_id: int,
    period_start: dt.date,
    period_end: dt.date,
    *,
    corner_id: int | None = None,
) -> list[ComboDay]:
    """기간 내 main_menu_id가 MAIN으로 나온 (날짜, 코너, 식사구분)마다, 같은
    슬롯의 SIDE 메뉴 목록과 그날 그 코너의 main_menu_id 평균 만족도를 묶는다.

    corner_id를 주면 그 코너에서 나온 슬롯만 본다 — 같은 메인이 여러 코너에서
    다른 부찬과 나오면 조합이 섞여 비교가 흐려지기 때문(2026-08 요청).
    """
    slot_filters = [
        WeeklyMenuPlan.menu_id == main_menu_id,
        WeeklyMenuPlan.menu_role == MenuRole.MAIN,
        WeeklyMenuPlan.plan_date.between(period_start, period_end),
    ]
    if corner_id is not None:
        slot_filters.append(WeeklyMenuPlan.corner_id == corner_id)
    main_slots = (
        db.query(WeeklyMenuPlan.plan_date, WeeklyMenuPlan.corner_id, WeeklyMenuPlan.meal_type)
        .filter(*slot_filters)
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
        # 평가 여부와 무관하게 그날 이 메뉴를 취식한 모든 행을 가져온다 — 만족도는
        # 그중 평가가 있는 것만 평균내고, 식수(headcount)는 전체 건수를 쓴다.
        rows = (
            db.query(MealLog.taste_score)
            .filter(
                MealLog.menu_id == main_menu_id,
                MealLog.corner_id == corner_id,
                MealLog.eaten_at >= day_start,
                MealLog.eaten_at < day_end,
            )
            .all()
        )
        score_values = [TASTE_SCORE_POINTS[s] for (s,) in rows if s is not None]
        results.append(
            ComboDay(
                plan_date=plan_date,
                side_menu_ids=frozenset(sides_by_slot.get((plan_date, corner_id, meal_type), set())),
                avg_satisfaction=statistics.fmean(score_values) if score_values else None,
                headcount=len(rows),
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
    headcounts_by_combo: dict[frozenset[int], list[int]] = {}
    for d in days:
        day_counts[d.side_menu_ids] = day_counts.get(d.side_menu_ids, 0) + 1
        if d.avg_satisfaction is not None:
            scores_by_combo.setdefault(d.side_menu_ids, []).append(d.avg_satisfaction)
        headcounts_by_combo.setdefault(d.side_menu_ids, []).append(d.headcount)

    results = [
        ComboSummary(
            side_menu_ids=combo,
            day_count=count,
            avg_satisfaction=(
                statistics.fmean(scores_by_combo[combo]) if combo in scores_by_combo else None
            ),
            avg_headcount=statistics.fmean(headcounts_by_combo[combo]),
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


# ---------------------------------------------------------------------------
# 기간 전체 일괄 조회 + 조합 편차 (2026-08)
# ---------------------------------------------------------------------------
# build_side_combos_for_main_menu는 슬롯마다 meal_log 쿼리를 1번씩 던진다.
# 단건 상세 조회엔 그게 더 가볍지만, "편차가 큰 메인메뉴 랭킹"처럼 기간 내 모든
# 메인을 훑어야 하는 화면에선 8개월 × 코너 7개 × 주 6일 = 1000+ 쿼리가 되어
# 못 쓴다. 그래서 쿼리 3개로 끝내고 메모리에서 묶는 배치 버전을 따로 둔다.
#
# 두 함수는 **같은 ComboDay를 내야 한다** — 랭킹과 상세가 다른 숫자를 보여주면
# 안 되므로 동치성 테스트로 고정한다(tests/test_api_ingest_and_analysis.py).


def build_side_combos_bulk(
    db: Session, period_start: dt.date, period_end: dt.date, *, corner_id: int | None = None
) -> dict[int, list[ComboDay]]:
    """기간 내 모든 메인메뉴에 대해 {main_menu_id: [ComboDay, ...]}를 만든다."""
    main_filters = [
        WeeklyMenuPlan.menu_role == MenuRole.MAIN,
        WeeklyMenuPlan.plan_date.between(period_start, period_end),
    ]
    if corner_id is not None:
        main_filters.append(WeeklyMenuPlan.corner_id == corner_id)
    main_slots = (
        db.query(
            WeeklyMenuPlan.menu_id,
            WeeklyMenuPlan.plan_date,
            WeeklyMenuPlan.corner_id,
            WeeklyMenuPlan.meal_type,
        )
        .filter(*main_filters)
        .distinct()
        .all()
    )
    if not main_slots:
        return {}

    side_rows = (
        db.query(
            WeeklyMenuPlan.plan_date,
            WeeklyMenuPlan.corner_id,
            WeeklyMenuPlan.meal_type,
            WeeklyMenuPlan.menu_id,
        )
        .filter(
            WeeklyMenuPlan.menu_role == MenuRole.SIDE,
            WeeklyMenuPlan.plan_date.between(period_start, period_end),
        )
        .all()
    )
    sides_by_slot: dict[tuple[dt.date, int, str], set[int]] = {}
    for plan_date, slot_corner_id, meal_type, menu_id in side_rows:
        sides_by_slot.setdefault((plan_date, slot_corner_id, meal_type), set()).add(menu_id)

    # 취식 기록은 (메뉴, 코너, 날짜)로 묶어 한 번에 읽는다. 단건 함수가 슬롯마다
    # 날짜 경계로 필터하던 것과 같은 범위를 여기서 한 번에 가져온다.
    log_start = dt.datetime.combine(period_start, dt.time())
    log_end = dt.datetime.combine(period_end, dt.time()) + dt.timedelta(days=1)
    log_rows = (
        db.query(MealLog.menu_id, MealLog.corner_id, MealLog.eaten_at, MealLog.taste_score)
        .filter(MealLog.eaten_at >= log_start, MealLog.eaten_at < log_end)
        .all()
    )
    logs_by_key: dict[tuple[int, int, dt.date], list] = {}
    for menu_id, log_corner_id, eaten_at, taste_score in log_rows:
        if menu_id is None:
            continue
        logs_by_key.setdefault((menu_id, log_corner_id, eaten_at.date()), []).append(taste_score)

    results: dict[int, list[ComboDay]] = {}
    for main_menu_id, plan_date, slot_corner_id, meal_type in main_slots:
        scores = logs_by_key.get((main_menu_id, slot_corner_id, plan_date), [])
        score_values = [TASTE_SCORE_POINTS[s] for s in scores if s is not None]
        results.setdefault(main_menu_id, []).append(
            ComboDay(
                plan_date=plan_date,
                side_menu_ids=frozenset(
                    sides_by_slot.get((plan_date, slot_corner_id, meal_type), set())
                ),
                avg_satisfaction=statistics.fmean(score_values) if score_values else None,
                headcount=len(scores),
            )
        )
    return results


# ---------------------------------------------------------------------------
# 부찬 → 메인 역방향 조회 (§80)
# ---------------------------------------------------------------------------
# build_side_combos_for_main_menu는 "이 메인이 언제 어떤 부찬과 나왔는지"를
# 본다. 여기는 반대 방향 — "이 부찬이 언제 어떤 코너의 어떤 메인과 나왔는지"
# 담당자 요청: "단무지 클릭 → 8/01 신포짜장면 / 8/11 스냅스낵 신라면"처럼
# 부찬 하나를 클릭해 상세 편성 이력을 보고 싶다는 것.


@dataclass(frozen=True)
class SideDishPairing:
    plan_date: dt.date
    corner_id: int
    meal_type: str
    main_menu_id: int | None
    main_avg_satisfaction: float | None


def find_main_menu_pairings_for_side_dish(
    db: Session,
    side_menu_id: int,
    period_start: dt.date,
    period_end: dt.date,
    *,
    corner_id: int | None = None,
) -> list[SideDishPairing]:
    """side_menu_id가 SIDE/HEALTH_GARDEN으로 나온 슬롯마다, 같은 슬롯의 MAIN
    메뉴와 그날 그 코너의 만족도를 묶는다.

    건강가든은 특정 코너 소속처럼 저장되지만 실제로는 코너 무관 공용이다
    (§132, menu_rotation.py와 동일 원칙) — 그래서 건강가든 슬롯은 그 날짜·
    식사구분의 모든 코너 MAIN과 매칭한다(어느 코너 손님이 가져갔는지 알 수
    없으므로 후보 전부를 보여준다). SIDE는 기존처럼 같은 코너의 MAIN만 본다.
    """
    side_filters = [
        WeeklyMenuPlan.menu_id == side_menu_id,
        WeeklyMenuPlan.menu_role.in_([MenuRole.SIDE, MenuRole.HEALTH_GARDEN]),
        WeeklyMenuPlan.plan_date.between(period_start, period_end),
    ]
    if corner_id is not None:
        side_filters.append(WeeklyMenuPlan.corner_id == corner_id)
    side_slots = (
        db.query(WeeklyMenuPlan.plan_date, WeeklyMenuPlan.corner_id, WeeklyMenuPlan.meal_type, WeeklyMenuPlan.menu_role)
        .filter(*side_filters)
        .distinct()
        .all()
    )
    if not side_slots:
        return []

    dates = {plan_date for plan_date, _, _, _ in side_slots}
    main_rows = (
        db.query(WeeklyMenuPlan.plan_date, WeeklyMenuPlan.corner_id, WeeklyMenuPlan.meal_type, WeeklyMenuPlan.menu_id)
        .filter(WeeklyMenuPlan.menu_role == MenuRole.MAIN, WeeklyMenuPlan.plan_date.in_(dates))
        .all()
    )
    main_by_slot: dict[tuple[dt.date, int, str], int] = {}
    main_by_date_meal: dict[tuple[dt.date, str], list[tuple[int, int]]] = {}
    for plan_date, main_corner_id, meal_type, menu_id in main_rows:
        main_by_slot[(plan_date, main_corner_id, meal_type)] = menu_id
        main_by_date_meal.setdefault((plan_date, meal_type), []).append((main_corner_id, menu_id))

    def _avg_satisfaction(main_menu_id: int, at_corner_id: int, plan_date: dt.date) -> float | None:
        day_start = dt.datetime.combine(plan_date, dt.time())
        day_end = day_start + dt.timedelta(days=1)
        rows = (
            db.query(MealLog.taste_score)
            .filter(
                MealLog.menu_id == main_menu_id,
                MealLog.corner_id == at_corner_id,
                MealLog.eaten_at >= day_start,
                MealLog.eaten_at < day_end,
            )
            .all()
        )
        score_values = [TASTE_SCORE_POINTS[s] for (s,) in rows if s is not None]
        return statistics.fmean(score_values) if score_values else None

    results = []
    for plan_date, slot_corner_id, meal_type, menu_role in side_slots:
        meal_type_value = meal_type.value
        if menu_role == MenuRole.HEALTH_GARDEN:
            candidates = main_by_date_meal.get((plan_date, meal_type_value), [])
            if not candidates:
                results.append(
                    SideDishPairing(
                        plan_date=plan_date, corner_id=slot_corner_id, meal_type=meal_type_value,
                        main_menu_id=None, main_avg_satisfaction=None,
                    )
                )
            for main_corner_id, main_menu_id in candidates:
                results.append(
                    SideDishPairing(
                        plan_date=plan_date,
                        corner_id=main_corner_id,
                        meal_type=meal_type_value,
                        main_menu_id=main_menu_id,
                        main_avg_satisfaction=_avg_satisfaction(main_menu_id, main_corner_id, plan_date),
                    )
                )
        else:
            main_menu_id = main_by_slot.get((plan_date, slot_corner_id, meal_type_value))
            results.append(
                SideDishPairing(
                    plan_date=plan_date,
                    corner_id=slot_corner_id,
                    meal_type=meal_type_value,
                    main_menu_id=main_menu_id,
                    main_avg_satisfaction=(
                        _avg_satisfaction(main_menu_id, slot_corner_id, plan_date) if main_menu_id is not None else None
                    ),
                )
            )
    results.sort(key=lambda p: p.plan_date)
    return results


def summarize_side_dish_pairings(pairings: list[SideDishPairing]) -> dict:
    """{avg_main_satisfaction, pairing_count} — compute_combo_satisfaction_summary
    와 같은 스타일(일자별 평균의 평균)."""
    scores = [p.main_avg_satisfaction for p in pairings if p.main_avg_satisfaction is not None]
    return {
        "avg_main_satisfaction": statistics.fmean(scores) if scores else None,
        "pairing_count": len(pairings),
    }


def compute_combo_spread(summaries: list[ComboSummary]) -> float | None:
    """순수 함수 — 조합별 만족도의 (최고 - 최저).

    편차가 크다 = 부찬을 바꾸면 만족도가 실제로 움직인다 = 손볼 가치가 있다.
    평가가 있는 조합이 2개 미만이면 비교 자체가 불가능하므로 None.
    """
    scored = [s.avg_satisfaction for s in summaries if s.avg_satisfaction is not None]
    if len(scored) < 2:
        return None
    return max(scored) - min(scored)
