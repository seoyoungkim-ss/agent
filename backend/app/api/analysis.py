import datetime as dt
import statistics
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.enums import (
    TASTE_SCORE_POINTS,
    Division,
    FoodVectorSource,
    MealType,
    MenuRole,
    TrendDirection,
)
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import CornerMaster, EmployeeMaster, MenuMaster
from app.models.stats import (
    DailyCornerStats,
    DailyDivisionStats,
    EmployeeTasteProfile,
    MenuPerformanceStats,
    TasteCluster,
)
from app.services.aggregation import (
    aggregate_daily_stats,
    aggregate_menu_performance,
    compute_menu_satisfaction_trends,
    diagnose_menu_decline,
)
from app.services.corner_core_layer import (
    build_employee_corner_counts,
    build_menu_controlled_meal_log_rows,
    classify_corner_core_layer,
    classify_menu_controlled_corner_preference,
)
from app.services.food_vector import (
    FOOD_VECTOR_DIMENSIONS,
    FOOD_VECTOR_LABELS_KO,
    compute_average_food_vector,
    describe_average_bias,
)
from app.services.food_vector_tagging import run_llm_food_vector_tagging, run_llm_ingredient_extraction
from app.services.holidays import DayClassification, HolidayService, family_day_dates_in_range
from app.services.llm_client import InternalLLMClient
from app.services.master_data import PLACEHOLDER_MENU_NAMES, TAKE_OUT_CORNER_NAME
from app.services.menu_name import pair_likely_same_menu
from app.services.menu_performance import (
    classify_menu_loyalty,
    classify_menu_quadrant,
    compute_menu_frequency,
    compute_menu_score,
    compute_share_of_traffic,
    compute_trend,
)
from app.services.menu_affinity import (
    build_employee_menu_sets,
    compute_menu_affinity,
    compute_top_menu_pairs,
    is_obvious_pair,
)
from app.services.menu_combination import (
    build_side_combos_bulk,
    build_side_combos_for_main_menu,
    compute_combo_nutrition_profile,
    compute_combo_satisfaction_summary,
    compute_combo_spread,
)
from app.services.menu_throughput import build_corner_daily_throughput, compute_menu_throughput_summary
from app.services.taste_clustering import compute_taste_clusters
from app.services.taste_profile import compute_employee_taste_profiles
from app.services.weekly_menu_prediction import compute_predicted_impact, compute_predicted_numbers_for_period
from app.services.menu_clash import find_ingredient_clashes, find_vector_clashes
from app.services.menu_plan_analytics import (
    classify_planning_action,
    compute_repertoire,
    median_or_zero,
)
from app.services.menu_rotation import (
    MIN_ROTATION_GAP_DAYS,
    ROTATION_WINDOW_DAYS,
    RotationFlag,
    classify_rotation,
    build_corner_menu_dates,
    count_in_window,
    find_overused_menus,
    is_over_frequency,
    max_in_window_for_role,
)
from app.services.weekly_menu_review import (
    add_feedback,
    build_weekly_menu_slots,
    list_feedback,
    parse_menu_names,
    set_health_garden_menus,
    set_menu_role,
)
from app.services.weekly_menu_role_llm import reclassify_weekly_menu_roles

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _period_bucket(stat_date: dt.date, granularity: str) -> str:
    if granularity == "monthly":
        return stat_date.strftime("%Y-%m")
    if granularity == "weekly":
        monday = stat_date - dt.timedelta(days=stat_date.weekday())
        return monday.isoformat()
    return stat_date.isoformat()


def _corner_id_by_menu_from_meal_log(
    db: Session, period_start: dt.date | None = None, period_end: dt.date | None = None
) -> dict[int, int]:
    """메뉴별로 실제 취식된 코너(최빈값)를 찾는다.

    weekly_menu_plan(주간 식단표)은 meal-log와 별도로 운영자가 직접 업로드해야
    하는 소스라 실사용 중 누락되기 쉽다(2026-07 실사용에서 전체 메뉴가
    "코너 미배정"으로 나오는 원인이었음) — meal_log.corner_id는 POS 취식기록
    자체에 이미 실려 있어 meal-log만 적재해도 항상 채워진다. 그래서 코너 배정은
    weekly_menu_plan 대신 meal_log에서 그 메뉴가 가장 많이 찍힌 코너를 쓴다.

    **요청 단위 캐시**: 이 함수는 180일치 meal_log를 GROUP BY 하는데,
    `_menu_popularity_multiplier`(simulation.py)가 코너·슬롯마다 호출해 한 화면에서
    수백 번 재실행됐다(2026-08 성능 조사). 같은 기간에 대한 결과는 요청 안에서
    변하지 않으므로 `Session.info`(SQLAlchemy가 세션 스코프 저장소로 제공)에
    담아 재사용한다 — 세션이 끝나면 같이 사라지므로 값이 오래되어 틀릴 일이 없다.
    """
    cache: dict = db.info.setdefault("_corner_id_by_menu_cache", {})
    cache_key = (period_start, period_end)
    if cache_key in cache:
        return cache[cache_key]

    query = db.query(MealLog.menu_id, MealLog.corner_id, func.count().label("cnt")).filter(
        MealLog.menu_id.isnot(None)
    )
    if period_start is not None and period_end is not None:
        period_start_dt = dt.datetime.combine(period_start, dt.time())
        period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
        query = query.filter(MealLog.eaten_at >= period_start_dt, MealLog.eaten_at < period_end_exclusive)
    rows = (
        query.group_by(MealLog.menu_id, MealLog.corner_id)
        .order_by(func.count().desc())
        .all()
    )
    corner_id_by_menu: dict[int, int] = {}
    for menu_id, corner_id, _cnt in rows:
        corner_id_by_menu.setdefault(menu_id, corner_id)  # count 내림차순이라 최빈 코너가 먼저 잡힘
    cache[cache_key] = corner_id_by_menu
    return corner_id_by_menu


def _apply_classification_filter(query, stat_date_col, is_holiday_col, classification, period_start, period_end):
    """평일/주말+공휴일/패밀리데이 공통 필터.

    is_holiday 컬럼은 boolean이라 3단계를 표현 못한다 — 패밀리데이는 기간 내
    날짜를 계산(family_day_dates_in_range)해 stat_date IN/NOT IN으로 거른다.
    "평일" 필터에서는 패밀리데이 날짜를 제외해 더는 평일 버킷에 안 섞이게 한다.
    """
    if classification == DayClassification.WEEKDAY.value:
        query = query.filter(is_holiday_col.is_(False))
        family_dates = family_day_dates_in_range(period_start, period_end)
        if family_dates:
            query = query.filter(stat_date_col.notin_(family_dates))
    elif classification == DayClassification.HOLIDAY.value:
        query = query.filter(is_holiday_col.is_(True))
    elif classification == DayClassification.FAMILY_DAY.value:
        family_dates = family_day_dates_in_range(period_start, period_end)
        query = query.filter(stat_date_col.in_(family_dates)) if family_dates else query.filter(False)
    return query


@router.get("/divisions")
def division_analysis(
    period_start: dt.date,
    period_end: dt.date,
    granularity: Literal["daily", "weekly", "monthly"] = "daily",
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일 | 패밀리데이"),
    db: Session = Depends(get_db),
):
    """PRD 6.1: 본사/계열사/기타 구분 일간/주간/월간 식수."""
    query = db.query(DailyDivisionStats).filter(
        DailyDivisionStats.stat_date.between(period_start, period_end)
    )
    query = _apply_classification_filter(
        query, DailyDivisionStats.stat_date, DailyDivisionStats.is_holiday, classification, period_start, period_end
    )

    totals: dict[tuple[str, str], int] = {}
    for row in query.all():
        key = (_period_bucket(row.stat_date, granularity), row.division.value)
        totals[key] = totals.get(key, 0) + row.headcount

    return [
        {"period": period, "division": division, "headcount": headcount}
        for (period, division), headcount in sorted(totals.items())
    ]


@router.get("/headcount-trend")
def headcount_trend(
    period_start: dt.date,
    period_end: dt.date,
    granularity: Literal["daily", "weekly", "monthly"] = "daily",
    group_by: Literal["total", "corner", "division", "meal_type"] = "total",
    meal_types: list[MealType] | None = Query(
        default=None, description="조식/중식/석식 필터 — 생략 시 전체"
    ),
    corner_ids: list[int] | None = Query(default=None, description="코너 필터 — 생략 시 전체"),
    divisions: list[Division] | None = Query(
        default=None, description="본사/계열사/기타 필터 — 생략 시 전체"
    ),
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일 | 패밀리데이"),
    db: Session = Depends(get_db),
):
    """현황 화면의 통합 식수 추이 — 조·중·석식 × 코너 × 회사구분 3축을 동시에 필터한다.

    **왜 집계 테이블을 안 쓰는가**: `daily_corner_stats`는 (날짜, 코너, 끼니),
    `daily_division_stats`는 (날짜, 회사구분, 끼니)로 각각 2축까지만 집계돼 있어
    "중식 × 한식코너 × 계열사" 같은 교차 셀이 어느 집계 테이블에도 없다. 3축이
    동시에 존재하는 유일한 소스가 원천 로그라서 `meal_log ⋈ employee_master`를
    요청 시점에 집계한다. 새 집계 테이블을 만드는 대신 이 방식을 택한 이유는
    이 레포가 집계 테이블 미갱신으로 화면이 비는 문제를 이미 두 번 겪었고
    (22절, 45절), meal_log에 eaten_at/corner_id/employee_id 인덱스가 이미
    있으며, 캠퍼스 1개 규모라 기간 스캔이 감당 가능하기 때문이다(2026-08).

    `group_by`는 **필터와 별개로** "무엇을 선으로 그릴지"를 정한다 — 예를 들어
    회사구분을 계열사로 좁힌 뒤 코너별로 나눠 보는 식의 조합이 가능하다.
    """
    period_start_dt = dt.datetime.combine(period_start, dt.time())
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())

    # 날짜 단위로 SQL에서 미리 집계한다. 예전엔 기간 내 취식 행을 **전부** 파이썬으로
    # 끌어와 세었는데(월간 선택 시 365일치 전량), 8개월치가 적재되면서 화면이 느려졌다
    # (2026-08 실사용 신고). 그룹 키는 (날짜, 코너, 끼니, 회사구분)이라 카디널리티가
    # 날짜×코너×3×3 수준으로 작고, 기간 버킷(주/월)은 그 위에서 접으면 된다.
    date_col = func.date(MealLog.eaten_at).label("stat_date")
    query = (
        db.query(
            date_col,
            MealLog.corner_id,
            MealLog.meal_type,
            EmployeeMaster.division,
            func.count().label("cnt"),
        )
        # 사번이 employee_master에 없을 수 있다 — aggregation.py::aggregate_daily_stats가
        # 그런 행을 Division.OTHER로 집계하므로(dict.get 기본값) 여기서도 버리지 않고
        # 같은 규칙으로 맞춰야 daily_division_stats와 합계가 어긋나지 않는다.
        .outerjoin(EmployeeMaster, MealLog.employee_id == EmployeeMaster.employee_id)
        .filter(MealLog.eaten_at >= period_start_dt, MealLog.eaten_at < period_end_exclusive)
        .group_by(date_col, MealLog.corner_id, MealLog.meal_type, EmployeeMaster.division)
    )
    if meal_types:
        query = query.filter(MealLog.meal_type.in_(meal_types))
    if corner_ids:
        query = query.filter(MealLog.corner_id.in_(corner_ids))
    if divisions:
        # 회사구분 필터는 SQL로 내린다. 단 Division.OTHER를 고른 경우엔 employee_master에
        # 없는 사번(division IS NULL)도 함께 잡아야 위 outerjoin 규칙과 일치한다.
        division_clause = EmployeeMaster.division.in_(divisions)
        if Division.OTHER in divisions:
            division_clause = or_(division_clause, EmployeeMaster.division.is_(None))
        query = query.filter(division_clause)

    corner_names = {c.corner_id: c.corner_name for c in db.query(CornerMaster).all()}
    # meal_log엔 is_holiday 컬럼이 없어 _apply_classification_filter(집계 테이블 전용)를
    # 못 쓴다. 대신 기간의 날짜별 분류를 한 번에 만들어 두고 조회한다 — 예전엔 취식
    # 행마다 classify()를 불러 같은 날짜를 그 날 취식 건수만큼 재계산했다.
    classification_by_date = (
        HolidayService(db).classify_range(period_start, period_end) if classification else {}
    )

    totals: dict[tuple[str, str, str], int] = {}
    for stat_date, corner_id, meal_type, division, cnt in query.all():
        # func.date()는 백엔드에 따라 date 또는 문자열을 준다 — 양쪽 다 받는다.
        if isinstance(stat_date, str):
            stat_date = dt.date.fromisoformat(stat_date)
        division = division or Division.OTHER
        if classification and classification_by_date.get(stat_date) is not None:
            if classification_by_date[stat_date].value != classification:
                continue

        if group_by == "corner":
            series_key, series_label = str(corner_id), corner_names.get(corner_id) or "코너 미배정"
        elif group_by == "division":
            series_key = series_label = division.value
        elif group_by == "meal_type":
            series_key = series_label = meal_type.value
        else:
            series_key = series_label = "전체"

        key = (_period_bucket(stat_date, granularity), series_key, series_label)
        totals[key] = totals.get(key, 0) + cnt

    return [
        {"period": period, "series_key": series_key, "series_label": series_label, "headcount": headcount}
        for (period, series_key, series_label), headcount in sorted(totals.items())
    ]


def _load_corner_stats(
    db: Session,
    period_start: dt.date,
    period_end: dt.date,
    classification: str | None,
    meal_types: list[MealType] | None = None,
) -> tuple[list[DailyCornerStats], dict[int, CornerMaster]]:
    query = db.query(DailyCornerStats).filter(DailyCornerStats.stat_date.between(period_start, period_end))
    query = _apply_classification_filter(
        query, DailyCornerStats.stat_date, DailyCornerStats.is_holiday, classification, period_start, period_end
    )
    if meal_types:
        query = query.filter(DailyCornerStats.meal_type.in_(meal_types))
    corners = {c.corner_id: c for c in db.query(CornerMaster).all()}
    return query.all(), corners


@router.get("/corners")
def corner_analysis(
    period_start: dt.date,
    period_end: dt.date,
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일 | 패밀리데이"),
    exclude_take_out: bool = Query(
        default=False, description="Take Out 코너 제외 — 착석 취식이 아니라 혼잡도/만족도 분석에 안 맞음"
    ),
    # 이 함수는 chat_grounding.py/dashboard.py에서 라우트가 아니라 일반 파이썬
    # 함수로도 직접 호출된다 — 그 경로에선 FastAPI가 Query() 기본값을 None으로
    # 못 풀어주므로 plain None을 써야 한다(Query 객체 그대로 들어오면 .in_()에서
    # 터짐, 2026-07).
    meal_types: list[MealType] | None = None,
    db: Session = Depends(get_db),
):
    """PRD 6.2: 코너별 이용자 수/만족도/피크타임 서브속도.

    그린미트(다이어트식, 매니아층 전용)는 항상 마지막 행으로 정렬한다 — 코너가
    나오는 화면 어디서든 일반 코너 비교에 섞이지 않도록.
    """
    rows, corners = _load_corner_stats(db, period_start, period_end, classification, meal_types)

    by_corner: dict[int, list[DailyCornerStats]] = {}
    for row in rows:
        by_corner.setdefault(row.corner_id, []).append(row)

    result = []
    for corner_id, stats in by_corner.items():
        corner = corners.get(corner_id)
        if exclude_take_out and corner and corner.corner_name == TAKE_OUT_CORNER_NAME:
            continue
        scores = [s.avg_taste_score for s in stats if s.avg_taste_score is not None]
        throughputs = [s.peak_throughput_per_min for s in stats if s.peak_throughput_per_min is not None]
        result.append(
            {
                "corner_id": corner_id,
                "corner_name": corner.corner_name if corner else None,
                "is_diet_corner": corner.is_diet_corner if corner else None,
                "headcount_total": sum(s.headcount for s in stats),
                "avg_taste_score": statistics.fmean(scores) if scores else None,
                "avg_peak_throughput_per_min": statistics.fmean(throughputs) if throughputs else None,
            }
        )
    result.sort(key=lambda r: (bool(r["is_diet_corner"]), -r["headcount_total"]))
    return result


@router.get("/corners/trend")
def corner_analysis_trend(
    period_start: dt.date,
    period_end: dt.date,
    granularity: Literal["daily", "weekly", "monthly"] = "weekly",
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일 | 패밀리데이"),
    exclude_take_out: bool = Query(default=False),
    meal_types: list[MealType] | None = Query(
        default=None, description="조식/중식/석식 중 선택 — 여러 개면 합산, 생략 시 전체 합산"
    ),
    db: Session = Depends(get_db),
):
    """PRD 6.2 확장: 코너별 만족도/피크타임 서브속도(및 식수)의 기간별(일간·주간·월간)
    추이. 홈 화면의 "코너별 주간 식수 추이"는 이 엔드포인트를 daily로 호출한다."""
    rows, corners = _load_corner_stats(db, period_start, period_end, classification, meal_types)

    buckets: dict[tuple[str, int], list[DailyCornerStats]] = {}
    for row in rows:
        corner = corners.get(row.corner_id)
        if exclude_take_out and corner and corner.corner_name == TAKE_OUT_CORNER_NAME:
            continue
        key = (_period_bucket(row.stat_date, granularity), row.corner_id)
        buckets.setdefault(key, []).append(row)

    result = []
    for (period, corner_id), stats in sorted(buckets.items()):
        corner = corners.get(corner_id)
        scores = [s.avg_taste_score for s in stats if s.avg_taste_score is not None]
        throughputs = [s.peak_throughput_per_min for s in stats if s.peak_throughput_per_min is not None]
        result.append(
            {
                "period": period,
                "corner_id": corner_id,
                "corner_name": corner.corner_name if corner else None,
                "is_diet_corner": corner.is_diet_corner if corner else None,
                "headcount": sum(s.headcount for s in stats),
                "avg_taste_score": statistics.fmean(scores) if scores else None,
                "avg_peak_throughput_per_min": statistics.fmean(throughputs) if throughputs else None,
            }
        )
    return result


@router.get("/corners/list")
def corner_list(db: Session = Depends(get_db)):
    """코너 목록만 — corner_master를 그대로 읽는다(통계 없음).

    `/analysis/corners`는 daily_corner_stats(배치 집계)를 읽어 배치가 안 돌면
    빈 배열이 된다. 현황 화면의 **코너 필터 선택지**는 배치 상태와 무관하게 항상
    떠 있어야 하므로(headcount-trend가 배치에 의존하지 않는 것과 같은 이유)
    마스터를 직접 읽는 경로를 따로 둔다(2026-08).
    """
    corners = db.query(CornerMaster).order_by(CornerMaster.corner_id).all()
    return [
        {"corner_id": c.corner_id, "corner_name": c.corner_name, "is_diet_corner": c.is_diet_corner}
        for c in corners
    ]


@router.get("/corners/main-menu-by-date")
def corner_main_menu_by_date(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    """코너×날짜별 메인메뉴명 — 코너별 분석 서브그래프의 날짜 툴팁에 "그날 뭐
    나왔는지" 붙이려는 용도(2026-07). weekly_menu_plan은 운영자가 별도 업로드해야
    해 누락될 수 있어(32절), 없는 날짜/코너는 응답에서 그냥 빠진다(프론트가
    없는 조합은 메뉴명 없이 표시).
    """
    rows = (
        db.query(WeeklyMenuPlan.corner_id, WeeklyMenuPlan.plan_date, MenuMaster.menu_name)
        .join(MenuMaster, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .filter(
            WeeklyMenuPlan.plan_date >= period_start,
            WeeklyMenuPlan.plan_date <= period_end,
            WeeklyMenuPlan.menu_role == MenuRole.MAIN,
        )
        .all()
    )
    return [
        {"corner_id": corner_id, "plan_date": plan_date.isoformat(), "menu_name": menu_name}
        for corner_id, plan_date, menu_name in rows
    ]


@router.get("/corners/{corner_id}/core-layer-menu-pairs")
def corner_core_layer_menu_pairs(
    corner_id: int,
    period_start: dt.date,
    period_end: dt.date,
    min_visit_count: int = 3,
    min_share: float = 0.3,
    min_co_count: int = 2,
    top_n: int = 10,
    db: Session = Depends(get_db),
):
    """PRD 6.2: 코너 코어층(반복 이용자) vs 나머지 인원의 메뉴 동반 선택 쌍 비교.

    lift는 각 그룹(코어층/나머지) 내부 모집단 기준으로 따로 계산되므로, 두 그룹의
    lift 수치를 직접 비교하면 안 된다 — co_count(동반 인원 수)만 그룹 간 비교에
    쓸 수 있다.
    """
    corner = db.get(CornerMaster, corner_id)
    if corner is None:
        raise HTTPException(status_code=404, detail="코너를 찾을 수 없습니다")

    employee_corner_counts = build_employee_corner_counts(db, period_start, period_end)
    core_results = classify_corner_core_layer(
        employee_corner_counts, corner_id, min_visit_count=min_visit_count, min_share=min_share
    )
    core_employee_ids = {r.employee_id for r in core_results}
    non_core_employee_ids = set(employee_corner_counts.keys()) - core_employee_ids

    employee_menus = build_employee_menu_sets(db, period_start, period_end)
    core_menus = {e: m for e, m in employee_menus.items() if e in core_employee_ids}
    non_core_menus = {e: m for e, m in employee_menus.items() if e in non_core_employee_ids}

    # 동반선택쌍의 각 메뉴가 어느 코너 소속인지 붙여준다 — "다른 코너 조합"을
    # 화면에서 구분해 보여주려는 목적(취식기록 기준 최빈 코너, weekly_menu_plan은
    # 누락되기 쉬워 안 씀 — _corner_id_by_menu_from_meal_log 관례와 동일).
    corner_id_by_menu_id = _corner_id_by_menu_from_meal_log(db, period_start, period_end)
    menu_id_by_name = {name: mid for mid, name in db.query(MenuMaster.menu_id, MenuMaster.menu_name).all()}
    corner_name_by_id = {c.corner_id: c.corner_name for c in db.query(CornerMaster).all()}
    # 같은 카테고리 메뉴끼리(예: 부대찌개+참치김치찌개)는 "자명한 조합"으로 표시해
    # 화면에서 뺄 수 있게 한다 — food_vector 코사인 유사도 기반(menu_affinity.py).
    food_vector_by_name = {
        m.menu_name: [float(x) for x in m.food_vector]
        for m in db.query(MenuMaster).all()
        if m.food_vector is not None
    }

    def _corner_name_for_menu(menu_name: str) -> str | None:
        menu_id = menu_id_by_name.get(menu_name)
        corner_id = corner_id_by_menu_id.get(menu_id) if menu_id is not None else None
        return corner_name_by_id.get(corner_id) if corner_id is not None else None

    def _serialize(pairs):
        return [
            {
                "menu_a": p.menu_a,
                "menu_b": p.menu_b,
                "co_count": p.co_count,
                "lift": p.lift,
                "corner_a": _corner_name_for_menu(p.menu_a),
                "corner_b": _corner_name_for_menu(p.menu_b),
                "is_obvious_pair": is_obvious_pair(
                    food_vector_by_name.get(p.menu_a), food_vector_by_name.get(p.menu_b)
                ),
            }
            for p in pairs
        ]

    def _cross_corner_top_pairs(employee_menus_subset: dict[str, set[str]]):
        # top_n 안에서만 자르면 같은 코너 조합이 워낙 흔해 다른 코너 조합이 거의
        # 안 보이므로, 후보 풀을 넉넉히 넓혀 계산한 뒤 다른 코너 조합만 걸러
        # top_n을 뽑는다.
        candidates = _serialize(
            compute_top_menu_pairs(employee_menus_subset, min_co_count=min_co_count, top_n=max(top_n * 20, 200))
        )
        cross = [p for p in candidates if p["corner_a"] and p["corner_b"] and p["corner_a"] != p["corner_b"]]
        return cross[:top_n]

    # 코너 충성도 신호 2번째 기준 — 같은 날 같은 메인메뉴가 여러 코너에서 동시
    # 제공된 경우, 메뉴가 같으니 코너 선택은 순수하게 코너 선호를 반영한다고 볼
    # 수 있다(PRD, 2026-07). 방문 빈도/비중(위 core_results)과는 다른 신호라
    # AND로 합치지 않고 별도 지표로 나란히 보여준다.
    menu_controlled_rows = build_menu_controlled_meal_log_rows(db, period_start, period_end)
    menu_controlled_preferences = classify_menu_controlled_corner_preference(menu_controlled_rows)
    this_corner_preference = menu_controlled_preferences.get(corner_id)

    return {
        "corner_id": corner_id,
        "corner_name": corner.corner_name,
        "menu_controlled_preference": (
            {
                "contested_occasions": this_corner_preference.contested_occasions,
                "chosen_count": this_corner_preference.chosen_count,
                "preference_ratio": round(this_corner_preference.preference_ratio, 3),
            }
            if this_corner_preference
            else None
        ),
        "core_layer": {
            "employee_count": len(core_employee_ids),
            "min_visit_count": min_visit_count,
            "min_share": min_share,
            "top_pairs": _serialize(
                compute_top_menu_pairs(core_menus, min_co_count=min_co_count, top_n=top_n)
            ),
            "cross_corner_pairs": _cross_corner_top_pairs(core_menus),
        },
        "non_core": {
            "employee_count": len(non_core_employee_ids),
            "top_pairs": _serialize(
                compute_top_menu_pairs(non_core_menus, min_co_count=min_co_count, top_n=top_n)
            ),
            "cross_corner_pairs": _cross_corner_top_pairs(non_core_menus),
        },
    }


@router.get("/corners/core-layer-summary")
def corner_core_layer_summary(
    period_start: dt.date,
    period_end: dt.date,
    min_visit_count: int = 3,
    min_share: float = 0.3,
    db: Session = Depends(get_db),
):
    """코너 코어층을 전체 코너 한 번에 비교하는 슬림 뷰.

    `corner_core_layer_menu_pairs`는 코너 하나씩 개별 호출해야 하고 메뉴 쌍
    계산까지 포함해 무겁다 — 비교 목적으로는 코어/유동 인원 수만 있으면
    되므로, `build_employee_corner_counts`(전체 코너를 이미 한 번에 스캔함)
    를 한 번만 호출한 뒤 코너별로 `classify_corner_core_layer`만 루프 돈다
    (메뉴 쌍 계산 생략).

    Take Out은 착석 취식이 아니라 "이 코너를 반복해서 찾는 충성 고객"이라는
    코어층 개념과 안 맞아 제외한다(2026-08) — corner_analysis의
    exclude_take_out과 같은 이유. 그린미트/미캠회관(전골)은 다른 코너별
    분석에서는 제외 대상이지만 코어층 분석 범위에는 포함되지 않아 이번엔
    건드리지 않는다.
    """
    take_out = db.query(CornerMaster).filter(CornerMaster.corner_name == TAKE_OUT_CORNER_NAME).one_or_none()
    exclude_corner_ids = {take_out.corner_id} if take_out else None
    corners = db.query(CornerMaster).filter(CornerMaster.corner_name != TAKE_OUT_CORNER_NAME).all()
    employee_corner_counts = build_employee_corner_counts(
        db, period_start, period_end, exclude_corner_ids=exclude_corner_ids
    )
    total_employees = len(employee_corner_counts)

    result = []
    for corner in corners:
        core_results = classify_corner_core_layer(
            employee_corner_counts, corner.corner_id, min_visit_count=min_visit_count, min_share=min_share
        )
        core_count = len(core_results)
        result.append(
            {
                "corner_id": corner.corner_id,
                "corner_name": corner.corner_name,
                "core_employee_count": core_count,
                "non_core_employee_count": total_employees - core_count,
            }
        )
    result.sort(key=lambda r: r["core_employee_count"], reverse=True)
    return result


@router.get("/corners/{corner_id}/menu-throughput")
def corner_menu_throughput(
    corner_id: int,
    period_start: dt.date,
    period_end: dt.date,
    min_day_count: int = 2,
    db: Session = Depends(get_db),
):
    """PRD 6.2: 그 코너에서 특정 메뉴가 나온 날의 피크타임 분당 서브 속도 비교.

    `daily_corner_stats`의 서브속도는 코너 단위라 메뉴 연관성을 볼 수 없다 —
    `meal_log`에서 날짜별 대표 메뉴(최빈 menu_id)를 구해 메뉴별 평균 처리량을
    `overall_avg_throughput`(기준선) 대비 오름차순(느린 메뉴 먼저)으로 반환한다.
    """
    corner = db.get(CornerMaster, corner_id)
    if corner is None:
        raise HTTPException(status_code=404, detail="코너를 찾을 수 없습니다")

    days = build_corner_daily_throughput(db, corner_id, period_start, period_end)
    summary = compute_menu_throughput_summary(days, min_day_count=min_day_count)
    menu_names = {m.menu_id: m.menu_name for m in db.query(MenuMaster).all()}

    return {
        "corner_id": corner_id,
        "corner_name": corner.corner_name,
        "overall_avg_throughput": summary.overall_avg_throughput,
        "menus": [
            {
                "menu_id": e.menu_id,
                "menu_name": menu_names.get(e.menu_id),
                "avg_throughput": e.avg_throughput,
                "day_count": e.day_count,
            }
            for e in summary.menus
        ],
    }


@router.get("/menu-performance")
def menu_performance(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    """PRD 6.3: 메뉴별 성과 (4분면 라벨 포함). 사전에 recompute가 호출돼 있어야 한다.

    corner_name은 meal_log에서 그 메뉴가 기간 내 가장 많이 찍힌 코너(최빈값)를
    붙인 것 — 프론트에서 메뉴가 너무 많을 때 코너별로 묶어 보여주는 용도다.
    """
    rows = (
        db.query(MenuPerformanceStats)
        .filter_by(period_start=period_start, period_end=period_end)
        .all()
    )
    menus = {m.menu_id: m.menu_name for m in db.query(MenuMaster).all()}
    corners = {c.corner_id: c.corner_name for c in db.query(CornerMaster).all()}
    corner_id_by_menu = _corner_id_by_menu_from_meal_log(db, period_start, period_end)

    return [
        {
            "menu_id": r.menu_id,
            "menu_name": menus.get(r.menu_id),
            "corner_name": corners.get(corner_id_by_menu.get(r.menu_id)),
            "appearance_count": r.appearance_count,
            "total_headcount": r.total_headcount,
            "evaluation_count": r.evaluation_count,
            "evaluation_rate": r.evaluation_rate,
            "raw_score": r.raw_score,
            "adjusted_score": r.adjusted_score,
            "share_of_traffic": r.share_of_traffic,
            "quadrant": r.quadrant_label.value if r.quadrant_label else None,
            "satisfaction_trend": r.satisfaction_trend.value if r.satisfaction_trend else None,
            "has_loyal_following": r.has_loyal_following,
        }
        for r in rows
    ]


@router.get("/menu-performance/by-meal-type")
def menu_performance_by_meal_type(
    period_start: dt.date, period_end: dt.date, meal_type: MealType, db: Session = Depends(get_db)
):
    """PRD 6.3 확장: 조식/중식/석식별 메뉴 4분면.

    `MenuPerformanceStats`(`/menu-performance`가 읽는 테이블)는 끼니 구분 없이
    전체를 통합해 사전 recompute한 값이라 끼니별로 나눌 수 없다 — 스키마
    마이그레이션 없이, `aggregate_menu_performance`(aggregation.py)와 동일한
    순수함수 체인(compute_menu_score/compute_menu_frequency/compute_share_
    of_traffic/classify_menu_quadrant)을 재사용하되 `meal_type` 필터를 추가해
    그 자리에서 계산만 하고 저장하지 않는다(기존 `MenuPerformanceStats`/
    `/menu-performance`는 그대로 유지, 하위호환). 수요/만족도 중앙값 기준도
    그 meal_type 내에서 다시 계산한다 — 끼니마다 분포가 다르기 때문.
    """
    settings = get_settings()
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    period_start_dt = dt.datetime.combine(period_start, dt.time())

    excluded_menu_ids = {
        menu_id
        for (menu_id,) in db.query(MenuMaster.menu_id).filter(MenuMaster.menu_name.in_(PLACEHOLDER_MENU_NAMES))
    }
    query = db.query(MealLog).filter(
        MealLog.eaten_at >= period_start_dt,
        MealLog.eaten_at < period_end_exclusive,
        MealLog.menu_id.isnot(None),
        MealLog.meal_type == meal_type,
    )
    if excluded_menu_ids:
        query = query.filter(MealLog.menu_id.notin_(excluded_menu_ids))
    logs = query.all()
    if not logs:
        return []

    total_headcount_all = len(logs)
    all_scores = [TASTE_SCORE_POINTS[log.taste_score] for log in logs if log.taste_score is not None]
    global_avg_score = statistics.fmean(all_scores) if all_scores else 3.0

    by_menu: dict[int, list[MealLog]] = {}
    employee_menu_counts: dict[str, dict[int, int]] = {}
    for log in logs:
        by_menu.setdefault(log.menu_id, []).append(log)
        # 로열티 판정용 — 이미 읽어둔 logs에서 바로 집계(새 쿼리 없음, 2026-07).
        employee_menu_counts.setdefault(log.employee_id, {})
        employee_menu_counts[log.employee_id][log.menu_id] = (
            employee_menu_counts[log.employee_id].get(log.menu_id, 0) + 1
        )

    menu_trend_by_id = compute_menu_satisfaction_trends(
        db, menu_ids=list(by_menu.keys()), period_end=period_end, settings=settings, meal_type=meal_type
    )

    prelim: dict[int, dict] = {}
    for menu_id, rows in by_menu.items():
        taste_scores = [r.taste_score for r in rows if r.taste_score is not None]
        score_result = compute_menu_score(
            taste_scores,
            global_avg_score=global_avg_score,
            shrinkage_m=settings.menu_score_shrinkage_m,
            low_sample_threshold=settings.menu_score_low_sample_threshold,
        )
        freq = compute_menu_frequency(
            [r.eaten_at.date() for r in rows],
            total_headcount=len(rows),
            evaluation_count=len(taste_scores),
        )
        demand = freq.total_headcount / freq.appearance_count if freq.appearance_count else 0.0
        prelim[menu_id] = {"score_result": score_result, "freq": freq, "demand": demand}

    demand_values = [v["demand"] for v in prelim.values()]
    score_values = [
        v["score_result"].adjusted_score for v in prelim.values() if v["score_result"].adjusted_score is not None
    ]
    demand_threshold = statistics.median(demand_values) if demand_values else 0.0
    score_threshold = statistics.median(score_values) if score_values else global_avg_score

    menus = {m.menu_id: m.menu_name for m in db.query(MenuMaster).all()}
    corners = {c.corner_id: c.corner_name for c in db.query(CornerMaster).all()}
    corner_id_by_menu = _corner_id_by_menu_from_meal_log(db, period_start, period_end)

    result = []
    for menu_id, data in prelim.items():
        score_result = data["score_result"]
        freq = data["freq"]
        share = compute_share_of_traffic(freq.total_headcount, total_headcount_all)
        loyal_employees = classify_menu_loyalty(
            employee_menu_counts,
            menu_id,
            freq.appearance_count,
            min_order_count=settings.menu_loyalty_min_order_count,
            min_order_ratio=settings.menu_loyalty_min_order_ratio,
        )
        has_loyal_following = len(loyal_employees) >= settings.menu_loyalty_min_employees
        satisfaction_trend = menu_trend_by_id.get(menu_id, TrendDirection.FLAT)
        quadrant = classify_menu_quadrant(
            demand=data["demand"],
            satisfaction=score_result.adjusted_score or global_avg_score,
            demand_threshold=demand_threshold,
            satisfaction_threshold=score_threshold,
            evaluation_count=score_result.evaluation_count,
            low_sample_threshold=settings.menu_score_low_sample_threshold,
            satisfaction_trend=satisfaction_trend,
            has_loyal_following=has_loyal_following,
        )
        result.append(
            {
                "menu_id": menu_id,
                "menu_name": menus.get(menu_id),
                "corner_name": corners.get(corner_id_by_menu.get(menu_id)),
                "appearance_count": freq.appearance_count,
                "total_headcount": freq.total_headcount,
                "evaluation_count": freq.evaluation_count,
                "evaluation_rate": freq.evaluation_rate,
                "raw_score": score_result.raw_score,
                "adjusted_score": score_result.adjusted_score,
                "share_of_traffic": share,
                "quadrant": quadrant.value,
                "satisfaction_trend": satisfaction_trend.value,
                "has_loyal_following": has_loyal_following,
            }
        )
    return result


def _top_menu_ids_by_count(menu_ids: list[int], top_n: int) -> list[tuple[int, int]]:
    """순수함수 — menu_id 목록에서 등장 빈도 상위 top_n개를 (menu_id, count)로 반환."""
    counts: dict[int, int] = {}
    for menu_id in menu_ids:
        counts[menu_id] = counts.get(menu_id, 0) + 1
    return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:top_n]


@router.get("/menus/top-by-headcount")
def top_menus_by_headcount(
    period_start: dt.date, period_end: dt.date, top_n: int = 10, db: Session = Depends(get_db)
):
    """기간 내 취식 건수(식수) 기준 메뉴 순위.

    `menu_performance`/`MenuPerformanceStats`는 사전에 recompute된 정확히
    일치하는 (period_start, period_end)만 조회 가능해 임의 기간(예: Agent
    채팅에서 "6월 가장 많이 먹은 메뉴" 같은 즉석 질의)에는 못 쓴다 — 이
    엔드포인트는 `meal_log`에서 그 자리에서 바로 집계해 임의 기간을 즉시
    조회한다(저장하지 않음, `aggregate_menu_performance`와 동일하게
    `PLACEHOLDER_MENU_NAMES` 제외).
    """
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    period_start_dt = dt.datetime.combine(period_start, dt.time())

    excluded_menu_ids = {
        menu_id
        for (menu_id,) in db.query(MenuMaster.menu_id).filter(MenuMaster.menu_name.in_(PLACEHOLDER_MENU_NAMES))
    }
    query = db.query(MealLog.menu_id).filter(
        MealLog.eaten_at >= period_start_dt,
        MealLog.eaten_at < period_end_exclusive,
        MealLog.menu_id.isnot(None),
    )
    if excluded_menu_ids:
        query = query.filter(MealLog.menu_id.notin_(excluded_menu_ids))
    menu_ids = [row[0] for row in query.all()]

    top = _top_menu_ids_by_count(menu_ids, top_n)
    menu_names = {m.menu_id: m.menu_name for m in db.query(MenuMaster).all()}
    return [{"menu_id": menu_id, "menu_name": menu_names.get(menu_id), "headcount": count} for menu_id, count in top]


@router.post("/daily-stats/recompute")
def recompute_daily_stats(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    """daily_corner_stats/daily_division_stats를 기간 전체에 대해 다시 계산한다.

    평소엔 스케줄러(app/scheduler.py::run_daily_batch)가 매일 새벽 전날 하루치만
    계산하지만, 취식 데이터를 과거 기간 한꺼번에(예: 6개월치 실사용 데이터)
    적재했을 때는 그 기간의 배치 집계가 통째로 비어 있어 홈/분석 화면에 데이터가
    안 보인다 — 이 엔드포인트로 날짜별로 한 번씩 다시 계산해 채운다.
    """
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end는 period_start 이후여야 합니다.")
    days_processed = 0
    current = period_start
    while current <= period_end:
        aggregate_daily_stats(db, current)
        days_processed += 1
        current += dt.timedelta(days=1)
    return {"days_processed": days_processed}


@router.post("/menu-performance/recompute")
def recompute_menu_performance(
    period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)
):
    updated = aggregate_menu_performance(db, period_start, period_end)
    return {"updated_menus": updated}


@router.get("/menu-performance/{menu_id}/decline-diagnosis")
def menu_decline_diagnosis(
    menu_id: int,
    recent_start: dt.date,
    recent_end: dt.date,
    prior_start: dt.date,
    prior_end: dt.date,
    db: Session = Depends(get_db),
):
    """PRD 6.3.3: 최근 기간 vs 이전 기간 비교로 식수 하락 원인을 진단한다."""
    diagnosis = diagnose_menu_decline(
        db, menu_id, (recent_start, recent_end), (prior_start, prior_end)
    )
    if diagnosis is None:
        raise HTTPException(
            status_code=404,
            detail="두 기간 모두 menu-performance/recompute가 먼저 실행돼 있어야 합니다.",
        )
    return {"menu_id": menu_id, "diagnosis": diagnosis.value}


@router.get("/users/{employee_id}/taste-profile")
def user_taste_profile(employee_id: str, db: Session = Depends(get_db)):
    """PRD 6.1: 개인 취향 벡터. food_vector와 같은 차원(FOOD_VECTOR_DIMENSIONS)."""
    profile = db.query(EmployeeTasteProfile).filter_by(employee_id=employee_id).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="취향 프로필이 없습니다. 먼저 recompute를 호출하세요.")
    cluster = db.get(TasteCluster, profile.cluster_id) if profile.cluster_id else None
    return {
        "employee_id": employee_id,
        "profile_vector": [float(x) for x in profile.profile_vector],
        "dimensions": FOOD_VECTOR_DIMENSIONS,
        "sample_size": profile.sample_size,
        "cluster_label": cluster.label if cluster else None,
    }


@router.post("/users/taste-profile/recompute")
def recompute_taste_profiles(db: Session = Depends(get_db)):
    updated = compute_employee_taste_profiles(db)
    return {"updated_employees": updated}


@router.get("/users/taste-clusters")
def taste_clusters(db: Session = Depends(get_db)):
    """PRD 6.1: 취향 군집 요약 목록 (사번 검색 없이 전체 경향을 보는 화면용)."""
    clusters = db.query(TasteCluster).order_by(TasteCluster.size.desc()).all()
    return [
        {
            "id": c.id,
            "label": c.label,
            "size": c.size,
            "centroid_vector": [float(x) for x in c.centroid_vector],
            "dimensions": FOOD_VECTOR_DIMENSIONS,
            "avg_satisfaction": c.avg_satisfaction,
            "top_menus": c.top_menus or [],
            "dominant_corner": c.dominant_corner,
        }
        for c in clusters
    ]


@router.post("/users/taste-clusters/recompute")
def recompute_taste_clusters(k: int = 5, db: Session = Depends(get_db)):
    created = compute_taste_clusters(db, k=k)
    if created == 0:
        raise HTTPException(
            status_code=400,
            detail=f"표본이 부족합니다 (군집 {k}개를 만들려면 최소 {k * 2}명의 취향 프로필이 필요). "
            "먼저 /users/taste-profile/recompute로 프로필을 충분히 쌓으세요.",
        )
    return {"clusters_created": created}


@router.get("/menus/food-vectors")
def list_menu_food_vectors(untagged_only: bool = False, db: Session = Depends(get_db)):
    """PRD 6.1: 관리자용 메뉴 food_vector 현황 — 수동 조정 화면에서 목록으로 쓴다.

    corner_name은 menu-performance와 같은 방식으로 meal_log에서 그 메뉴가
    (기간 제한 없이 전체에서) 가장 많이 찍힌 코너(최빈값)를 붙인 것 — 프론트가
    메뉴 목록을 코너별로 묶어 보여주는 용도다.
    """
    query = db.query(MenuMaster)
    if untagged_only:
        query = query.filter(MenuMaster.food_vector.is_(None))
    menus = query.order_by(MenuMaster.menu_name).all()

    corners = {c.corner_id: c.corner_name for c in db.query(CornerMaster).all()}
    corner_id_by_menu = _corner_id_by_menu_from_meal_log(db)

    return [
        {
            "menu_id": m.menu_id,
            "menu_name": m.menu_name,
            "corner_name": corners.get(corner_id_by_menu.get(m.menu_id)),
            "food_vector": [float(x) for x in m.food_vector] if m.food_vector is not None else None,
            "dimensions": FOOD_VECTOR_DIMENSIONS,
            "source": m.food_vector_source.value if m.food_vector_source else None,
        }
        for m in menus
    ]


@router.get("/menus/food-vectors/average")
def average_menu_food_vector(db: Session = Depends(get_db)):
    """캠퍼스 내 전체 메인메뉴의 평균 food_vector — 어떤 맛 편향으로 쏠려 있는지
    한눈에 보려는 용도(음식벡터 관리 화면 상단 레이더 차트).

    메인메뉴만 대상으로 한다(부찬은 메뉴 성향을 대표하지 않음) — weekly_menu_plan에
    MAIN으로 한 번이라도 등장한 menu_id만 고른다.
    """
    main_menu_ids = {
        row.menu_id
        for row in db.query(WeeklyMenuPlan.menu_id).filter(WeeklyMenuPlan.menu_role == MenuRole.MAIN).distinct().all()
    }
    vectors = [
        [float(x) for x in m.food_vector]
        for m in db.query(MenuMaster).filter(MenuMaster.food_vector.isnot(None)).all()
        if m.menu_id in main_menu_ids
    ]
    average = compute_average_food_vector(vectors)
    return {
        "dimensions": FOOD_VECTOR_DIMENSIONS,
        "labels_ko": FOOD_VECTOR_LABELS_KO,
        "average": average,
        "sample_size": len(vectors),
        "bias_description": describe_average_bias(average) if vectors else None,
    }


class FoodVectorUpdateRequest(BaseModel):
    vector: list[float]


@router.put("/menus/{menu_id}/food-vector")
def update_menu_food_vector(
    menu_id: int, payload: FoodVectorUpdateRequest, db: Session = Depends(get_db)
):
    """PRD 6.1: 관리자가 규칙/LLM 태깅 결과를 수동으로 덮어쓴다.

    source=MANUAL로 표시되면 이후 규칙(신메뉴 인입 시엔 이미 다른 메뉴라 해당 없음)/
    LLM 재태깅 배치가 건드리지 않는다 — 두 배치 모두 food_vector가 NULL인 메뉴만
    고르는데, 수동 조정 후에는 NULL이 아니게 되므로 자동으로 보호된다.
    """
    menu = db.get(MenuMaster, menu_id)
    if menu is None:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다")
    if len(payload.vector) != len(FOOD_VECTOR_DIMENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"vector는 {len(FOOD_VECTOR_DIMENSIONS)}개 값이어야 합니다: {FOOD_VECTOR_DIMENSIONS}",
        )
    if any(v < 0.0 or v > 1.0 for v in payload.vector):
        raise HTTPException(status_code=400, detail="각 값은 0.0~1.0 범위여야 합니다")

    menu.food_vector = payload.vector
    menu.food_vector_source = FoodVectorSource.MANUAL
    db.commit()
    return {
        "menu_id": menu_id,
        "food_vector": payload.vector,
        "dimensions": FOOD_VECTOR_DIMENSIONS,
        "source": FoodVectorSource.MANUAL.value,
    }


class NewMenuStatusUpdateRequest(BaseModel):
    menu_name: str
    is_new: bool | None  # True=강제 신메뉴 노출, False=강제 제외, null=자동판정으로 되돌림


@router.put("/menus/new-menu-status")
def update_new_menu_status(payload: NewMenuStatusUpdateRequest, db: Session = Depends(get_db)):
    """PRD 5.3: 홈 "신메뉴 반응"의 자동판정(weekly_menu_plan.is_new_menu, 최근
    30일 창)을 관리자가 직접 뒤집는다 — 자동판정이 인제스트 순서에 따라
    깨지기 쉽고, 30일이 지나면 강제로 빠지는 문제를 관리자가 직접 보정할 수
    있게 한다(2026-07 실사용 요청).
    """
    menu = db.query(MenuMaster).filter(MenuMaster.menu_name == payload.menu_name).first()
    if menu is None:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다")

    menu.new_menu_override = payload.is_new
    menu.new_menu_marked_on = dt.date.today() if payload.is_new is not None else None
    db.commit()
    return {
        "menu_id": menu.menu_id,
        "menu_name": menu.menu_name,
        "new_menu_override": menu.new_menu_override,
        "new_menu_marked_on": menu.new_menu_marked_on.isoformat() if menu.new_menu_marked_on else None,
    }


@router.post("/menus/extract-ingredients-with-llm")
async def extract_ingredients_with_llm(db: Session = Depends(get_db)):
    """식재료가 아직 비어 있는 메뉴만 LLM으로 채운다 (2026-08).

    한 끼 구성의 재료 중복 판정이 키워드 사전만 쓰면 사전에 없는 재료를 못 잡고,
    원산지 문자열이 남아 있으면 재료로 오인한다. food_vector 태깅과 완전히 같은
    3단계(규칙 → LLM → 관리자수동) 구조라 배선이 같다.
    """
    updated = await run_llm_ingredient_extraction(db, InternalLLMClient(get_settings()))
    return {"updated": updated}


@router.post("/menus/tag-with-llm")
async def tag_menus_with_llm(db: Session = Depends(get_db)):
    """PRD 6.1: 규칙 기반으로 태깅 못 한(food_vector NULL) 메뉴를 사내 LLM으로 보강한다."""
    client = InternalLLMClient(get_settings())
    tagged = await run_llm_food_vector_tagging(db, client)
    return {"tagged_menus": tagged}


def _serialize_weekly_menu_item(item) -> dict | None:
    if item is None:
        return None
    return {"plan_id": item.plan_id, "menu_id": item.menu_id, "menu_name": item.menu_name, "role_source": item.role_source}


@router.get("/weekly-menu")
def list_weekly_menu(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    """주간 식단표 검토/관리 화면: 그 기간의 (날짜, 코너, 식사구분)별 주찬/부찬과
    개선의견 제출 마감(plan_date - 7일) 정보를 반환한다."""
    slots = build_weekly_menu_slots(db, period_start, period_end)
    return [
        {
            "plan_date": s.plan_date.isoformat(),
            "corner_id": s.corner_id,
            "corner_name": s.corner_name,
            "meal_type": s.meal_type,
            "main": _serialize_weekly_menu_item(s.main),
            "sides": [_serialize_weekly_menu_item(item) for item in s.sides],
            "health_garden": [_serialize_weekly_menu_item(item) for item in s.health_garden],
            "feedback_deadline": s.feedback_deadline.isoformat(),
            "is_past_deadline": s.is_past_deadline,
        }
        for s in slots
    ]


class HealthGardenUpdateRequest(BaseModel):
    plan_date: dt.date
    corner_id: int
    meal_type: MealType
    # 쉼표/줄바꿈/탭으로 구분된 메뉴명. 빈 문자열이면 그 슬롯의 건강가든을 비운다.
    menu_names_raw: str


@router.put("/weekly-menu/health-garden")
def update_health_garden(payload: HealthGardenUpdateRequest, db: Session = Depends(get_db)):
    """건강가든 메뉴를 담당자가 텍스트로 직접 입력한다(2026-08 협의 결정).

    식단표 엑셀에 건강가든이 아직 없어 정식 파싱 경로가 없다. "대략 5개 종류가
    반복"이라는 운영 현실에 맞춰 텍스트 입력으로 우선 받고, weekly_menu_plan에
    HEALTH_GARDEN 역할로 적재해 회전 이력·중복 판정이 메인/부찬과 함께 돌게 한다.
    PUT인 이유는 슬롯 단위 **전체 교체**라서다(POST 추가가 아님).
    """
    corner = db.get(CornerMaster, payload.corner_id)
    if corner is None:
        raise HTTPException(status_code=404, detail="코너를 찾을 수 없습니다")

    names = parse_menu_names(payload.menu_names_raw)
    rows = set_health_garden_menus(
        db, payload.plan_date, payload.corner_id, payload.meal_type, names
    )
    menu_names = {
        m.menu_id: m.menu_name
        for m in db.query(MenuMaster).filter(MenuMaster.menu_id.in_([r.menu_id for r in rows])).all()
    } if rows else {}
    return {
        "plan_date": payload.plan_date.isoformat(),
        "corner_id": payload.corner_id,
        "meal_type": payload.meal_type.value,
        "items": [
            {"plan_id": r.id, "menu_id": r.menu_id, "menu_name": menu_names.get(r.menu_id)}
            for r in rows
        ],
    }


@router.get("/weekly-menu/combination-check")
def weekly_menu_combination_check(
    period_start: dt.date,
    period_end: dt.date,
    db: Session = Depends(get_db),
):
    """한 끼 구성 안에서 메인·부찬·건강가든의 재료·특성이 겹치는지 진단한다
    (2026-08 요청). 판정은 `app/services/menu_clash.py`의 순수 함수가 한다.

    `/weekly-menu/rotation`과 축이 다르다 — 저쪽은 "이 메뉴 최근에 또 내보내지
    않았나"(기간 내 같은 메뉴 반복), 이쪽은 "이 한 끼 구성이 겹치지 않나".

    건강가든도 부찬과 함께 넣어 본다(요청이 "메인/부찬/건강가든 조합"이었다).
    """
    slots = build_weekly_menu_slots(db, period_start, period_end)
    if not slots:
        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "slots": [],
            "untagged_menu_count": 0,
        }

    # food_vector를 슬롯마다 조회하면 N+1이 되므로 등장 메뉴를 한 번에 읽는다.
    menu_ids = {
        item.menu_id
        for s in slots
        for item in [*( [s.main] if s.main else []), *s.sides, *s.health_garden]
    }
    vectors: dict[int, list[float] | None] = {}
    # 재료는 menu_master.ingredients(규칙→LLM→수동 3단계로 채운 값)를 우선 쓴다.
    # 비어 있으면 menu_clash가 이름 기반 규칙으로 폴백한다(2026-08).
    ingredients_by_name: dict[str, list[str]] = {}
    if menu_ids:
        for m in db.query(MenuMaster).filter(MenuMaster.menu_id.in_(menu_ids)).all():
            vectors[m.menu_id] = [float(x) for x in m.food_vector] if m.food_vector is not None else None
            if m.ingredients:
                ingredients_by_name[m.menu_name] = list(m.ingredients)

    results = []
    untagged_all: set[str] = set()
    for s in slots:
        # 부찬과 건강가든을 함께 "곁들임"으로 본다 — 먹는 사람에겐 둘 다
        # 메인 옆에 놓이는 반찬이라 중복 여부 판단이 같다.
        accompaniments = [*s.sides, *s.health_garden]
        main_name = s.main.menu_name if s.main else None

        ingredient_clashes = find_ingredient_clashes(
            main_name,
            [item.menu_name for item in accompaniments],
            ingredients_by_name=ingredients_by_name,
        )
        vector_clashes, untagged = find_vector_clashes(
            (s.main.menu_name, vectors.get(s.main.menu_id)) if s.main else None,
            [(item.menu_name, vectors.get(item.menu_id)) for item in accompaniments],
        )
        untagged_all.update(untagged)

        results.append(
            {
                "plan_date": s.plan_date.isoformat(),
                "corner_id": s.corner_id,
                "corner_name": s.corner_name,
                "meal_type": s.meal_type,
                "main": main_name,
                "sides": [item.menu_name for item in s.sides],
                "health_garden": [item.menu_name for item in s.health_garden],
                "ingredient_clashes": [
                    {"menu_a": c.menu_a, "menu_b": c.menu_b, "shared": c.shared}
                    for c in ingredient_clashes
                ],
                "vector_clashes": [
                    {
                        "menu_a": c.menu_a,
                        "menu_b": c.menu_b,
                        "dimension": c.dimension,
                        "label_ko": c.label_ko,
                        "value_a": c.value_a,
                        "value_b": c.value_b,
                    }
                    for c in vector_clashes
                ],
                "untagged": untagged,
            }
        )

    # 충돌이 많은 슬롯을 위로 — 담당자가 고쳐야 할 것부터 보여야 한다.
    results.sort(
        key=lambda r: (
            -(len(r["ingredient_clashes"]) + len(r["vector_clashes"])),
            r["plan_date"],
            r["corner_name"],
        )
    )
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "slots": results,
        "untagged_menu_count": len(untagged_all),
    }


@router.get("/weekly-menu/rotation")
def weekly_menu_rotation(
    period_start: dt.date,
    period_end: dt.date,
    lookback_days: int = 180,
    db: Session = Depends(get_db),
):
    """메뉴 회전 이력 — 조회 기간에 편성된 메뉴들이 직전 편성 이후 얼마 만에
    다시 나오는지 판정한다(2순위 "중복 편성 최소화", 2026-08).

    과거 이력은 weekly_menu_plan(편성 이력)에서 본다 — meal_log(취식 이력)가
    아니다. "언제 또 내보낼까"를 정하는 편성 담당자 관점에선 실제로 몇 명이
    먹었는지가 아니라 **식단표에 몇 번 올렸는지**가 기준이기 때문이다.

    판정 대상에는 메인/부찬/건강가든을 모두 넣는다(요청: "메인메뉴/부찬/건강가든
    메뉴 조합 중복 최소화").
    """
    history_start = period_start - dt.timedelta(days=lookback_days)
    rows = (
        db.query(
            WeeklyMenuPlan.plan_date,
            WeeklyMenuPlan.menu_id,
            MenuMaster.menu_name,
            WeeklyMenuPlan.menu_role,
            WeeklyMenuPlan.corner_id,
            CornerMaster.corner_name,
            WeeklyMenuPlan.meal_type,
        )
        .join(MenuMaster, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .join(CornerMaster, WeeklyMenuPlan.corner_id == CornerMaster.corner_id)
        .filter(WeeklyMenuPlan.plan_date >= history_start, WeeklyMenuPlan.plan_date <= period_end)
        .all()
    )

    # (코너, 메뉴)별 전체 편성일(과거 + 조회 기간).
    #
    # ⚠️ 코너를 키에 넣는다(2026-08 담당자 기준): "포기김치가 다른 코너에서 각각
    # 나왔다고 중복이면 안 된다." 예전엔 메뉴만으로 묶어서 다른 코너에 같은 날 깔린
    # 게 SAME_DAY 경고로 떴는데, 이제 그건 중복이 아니다. 건강가든은 공용이라
    # 예외로 모든 코너에 합쳐진다 — `build_corner_menu_dates`가 그 규칙을 담는다.
    # 같은 화면의 회전 이력과 과다 편성이 서로 다른 기준을 쓰면 안 되므로 둘 다
    # 이 집합을 쓴다(§55.2에서 겪은 문제).
    all_planned: list[tuple[dt.date, str, str, str]] = [
        (
            plan_date,
            corner_name,
            menu_name,
            menu_role.value if hasattr(menu_role, "value") else str(menu_role),
        )
        for plan_date, _menu_id, menu_name, menu_role, _corner_id, corner_name, _meal_type in rows
    ]
    dates_by_corner_menu = build_corner_menu_dates(all_planned)

    results = []
    planned_in_period: list[tuple[dt.date, str, str, str]] = []
    for plan_date, menu_id, menu_name, menu_role, corner_id, corner_name, meal_type in rows:
        if plan_date < period_start:
            continue  # 과거 이력은 판정 기준으로만 쓰고 결과에는 안 넣는다
        role_value = menu_role.value if hasattr(menu_role, "value") else str(menu_role)
        planned_in_period.append((plan_date, corner_name, menu_name, role_value))
        menu_dates = dates_by_corner_menu.get((corner_name, menu_name), [])
        verdict = classify_rotation(plan_date, menu_dates)
        results.append(
            {
                "plan_date": plan_date.isoformat(),
                "corner_id": corner_id,
                "corner_name": corner_name,
                "meal_type": meal_type.value if hasattr(meal_type, "value") else str(meal_type),
                "menu_id": menu_id,
                "menu_name": menu_name,
                "menu_role": role_value,
                "flag": verdict.flag.value,
                "gap_days": verdict.gap_days,
                "avg_interval_days": (
                    round(verdict.avg_interval_days, 1) if verdict.avg_interval_days is not None else None
                ),
                "previous_date": verdict.previous_date.isoformat() if verdict.previous_date else None,
                # 횟수 기준(담당자: "3개월에 2회까지는 무난") — 간격 기준과 성격이
                # 달라 따로 싣는다. "14일은 넘겼지만 분기에 5번"은 간격으론 안 잡힌다.
                "window_count": count_in_window(plan_date, menu_dates),
                "window_max": max_in_window_for_role(role_value),
                "over_frequency": is_over_frequency(plan_date, menu_dates, role_value),
            }
        )

    # 경고부터 위로 — 담당자가 고쳐야 할 것이 먼저 보여야 한다.
    flag_order = {
        RotationFlag.SAME_DAY.value: 0,
        RotationFlag.TOO_SOON.value: 1,
        RotationFlag.EARLY.value: 2,
        RotationFlag.LONG_ABSENT.value: 3,
        RotationFlag.FIRST_TIME.value: 4,
        RotationFlag.NORMAL.value: 5,
    }
    results.sort(key=lambda r: (flag_order.get(r["flag"], 9), r["plan_date"], r["corner_name"]))

    overused = find_overused_menus(planned_in_period)
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "lookback_days": lookback_days,
        "min_rotation_gap_days": MIN_ROTATION_GAP_DAYS,
        "rotation_window_days": ROTATION_WINDOW_DAYS,
        "items": results,
        "overused": [
            {
                "menu_name": o.menu_name,
                "menu_role": o.menu_role,
                "corner_name": o.corner_name,
                "count": o.count,
                "dates": [d.isoformat() for d in o.dates],
            }
            for o in overused
        ],
    }


class MenuRoleUpdateRequest(BaseModel):
    menu_role: MenuRole


@router.put("/weekly-menu/{plan_id}/role")
def update_weekly_menu_role(plan_id: int, payload: MenuRoleUpdateRequest, db: Session = Depends(get_db)):
    """관리자가 셀 병합 등으로 잘못 판별된 주찬/부찬을 직접 고친다.

    role_source가 "관리자수동"으로 잠겨 이후 LLM 일괄 재분류가 이 행을 건드리지
    않는다(food_vector 관리자수동 잠금과 동일한 보호 방식).
    """
    plan = set_menu_role(db, plan_id, payload.menu_role)
    if plan is None:
        raise HTTPException(status_code=404, detail="식단표 항목을 찾을 수 없습니다")
    return {"plan_id": plan.id, "menu_role": plan.menu_role.value, "role_source": plan.role_source.value}


class WeeklyMenuFeedbackRequest(BaseModel):
    plan_date: dt.date
    corner_id: int
    comment: str


@router.post("/weekly-menu/feedback")
def create_weekly_menu_feedback(payload: WeeklyMenuFeedbackRequest, db: Session = Depends(get_db)):
    """관리자가 주간 식단표에 남기는 개선의견 — 마감(plan_date - 7일)이 지나도
    저장은 항상 가능하다(이력으로 남김), 화면에서 마감 여부만 배지로 알려준다."""
    corner = db.get(CornerMaster, payload.corner_id)
    if corner is None:
        raise HTTPException(status_code=404, detail="코너를 찾을 수 없습니다")
    feedback = add_feedback(db, payload.plan_date, payload.corner_id, payload.comment)
    return {
        "id": feedback.id,
        "plan_date": feedback.plan_date.isoformat(),
        "corner_id": feedback.corner_id,
        "comment": feedback.comment,
        "created_at": feedback.created_at.isoformat(),
    }


@router.get("/weekly-menu/feedback")
def list_weekly_menu_feedback(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    corners = {c.corner_id: c.corner_name for c in db.query(CornerMaster).all()}
    feedback_rows = list_feedback(db, period_start, period_end)
    return [
        {
            "id": f.id,
            "plan_date": f.plan_date.isoformat(),
            "corner_id": f.corner_id,
            "corner_name": corners.get(f.corner_id),
            "comment": f.comment,
            "created_at": f.created_at.isoformat(),
        }
        for f in feedback_rows
    ]


@router.post("/weekly-menu/reclassify-roles-with-llm")
async def reclassify_weekly_menu_roles_endpoint(
    period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)
):
    """규칙 기반으로 나뉜(role_source != 관리자수동) 주찬/부찬을 사내 LLM으로
    일괄 재분류한다. 관리자가 수동으로 고친 행은 건드리지 않는다."""
    client = InternalLLMClient(get_settings())
    reclassified = await reclassify_weekly_menu_roles(db, client, period_start, period_end)
    return {"reclassified_slots": reclassified}


def _serialize_predicted_numbers(numbers: dict) -> dict:
    """compute_predicted_numbers(_for_period)가 돌려주는 dict의 plan_date/
    meal_type만 JSON 직렬화 가능한 값으로 바꾼다 — 서비스 계층은 원본 파이썬
    타입(date/enum)을 그대로 쓰고, API 계층에서 변환하는 이 레포의 관례."""
    return {
        **numbers,
        "plan_date": numbers["plan_date"].isoformat(),
        "meal_type": numbers["meal_type"].value,
    }


@router.get("/weekly-menu/{plan_id}/predicted-impact")
async def weekly_menu_predicted_impact(plan_id: int, db: Session = Depends(get_db)):
    """PRD 7: 이 슬롯(메인메뉴)의 기존 성적 + 예상 점유율/식수 + LLM 정성 코멘트.

    쿼리/LLM 호출 비용 때문에 목록 조회에서는 계산하지 않고, 프론트에서 "예측
    보기" 버튼을 눌렀을 때만 호출한다(2026-07 사용자 확인).
    """
    client = InternalLLMClient(get_settings())
    result = await compute_predicted_impact(db, client, plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="메인메뉴로 지정된 주간 식단표 항목을 찾을 수 없습니다")
    return _serialize_predicted_numbers(result)


@router.get("/weekly-menu/predicted-impact-summary")
def weekly_menu_predicted_impact_summary(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    """PRD 7: 그 기간 전체 메인메뉴 슬롯의 예상 점유율/식수를 LLM 없이 한 번에
    계산한다 — 주간 식단표 격자표의 "전체 예측 비교" 버튼용(2026-07). 슬롯이
    많아 상세(LLM 코멘트)보다는 무겁지만, 이것도 버튼 클릭 시에만 호출한다.
    """
    numbers_list = compute_predicted_numbers_for_period(db, period_start, period_end)
    return [_serialize_predicted_numbers(n) for n in numbers_list]


@router.get("/menu-affinity/{menu_name}")
def menu_affinity(
    menu_name: str,
    period_start: dt.date,
    period_end: dt.date,
    min_co_count: int = 3,
    top_n: int = 10,
    db: Session = Depends(get_db),
):
    """PRD 6.1: 이 메뉴를 먹는 사람이 같이/대신 자주 고르는 메뉴 (동반 선택 경향성)."""
    employee_menus = build_employee_menu_sets(db, period_start, period_end)
    results = compute_menu_affinity(
        employee_menus, menu_name, min_co_count=min_co_count, top_n=top_n
    )
    if not results and menu_name not in {m for menus in employee_menus.values() for m in menus}:
        raise HTTPException(
            status_code=404, detail=f"'{menu_name}' 메뉴의 취식 기록이 이 기간에 없습니다."
        )
    return [{"menu_name": r.menu_name, "co_count": r.co_count, "lift": r.lift} for r in results]


@router.get("/menu-plan/performance")
def menu_plan_performance(
    period_start: dt.date,
    period_end: dt.date,
    meal_type: MealType | None = None,
    corner_id: int | None = None,
    db: Session = Depends(get_db),
):
    """편성 횟수 × 반응 — "다음 주 뭘 빼고 뭘 넣을까"에 답한다 (2026-08).

    **메인메뉴만 본다.** 맛평가·취식 데이터는 그 사람이 고른 **메인** 기준이고
    부찬은 취식 기록에 따로 안 남는다(담당자 확인) — 부찬을 넣으면 전부 취식 0이
    되어 무의미하다.

    기존 4분면(`/menu-performance`)과 결정적으로 다른 점: 저쪽 X축은 `meal_log`의
    취식 발생 일수라 **편성했는데 아무도 안 먹은 메뉴가 아예 안 나타난다.**
    여기선 `weekly_menu_plan` 기준이라 그게 보이고, 그게 가장 강한 감편 신호다.

    응답의 `matching`은 식단표 메뉴명과 취식기록 메뉴명이 실제로 이어졌는지를
    보여준다. 표기가 달라 매칭이 안 된 메뉴가 "아무도 안 먹은 메뉴"로 둔갑해
    감편 리스트를 오염시키는 걸 담당자가 직접 걸러낼 수 있어야 한다.
    """
    plan_filters = [
        WeeklyMenuPlan.menu_role == MenuRole.MAIN,
        WeeklyMenuPlan.plan_date.between(period_start, period_end),
    ]
    if meal_type is not None:
        plan_filters.append(WeeklyMenuPlan.meal_type == meal_type)
    if corner_id is not None:
        plan_filters.append(WeeklyMenuPlan.corner_id == corner_id)

    plan_rows = (
        db.query(WeeklyMenuPlan.menu_id, MenuMaster.menu_name, WeeklyMenuPlan.plan_date)
        .join(MenuMaster, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .filter(*plan_filters)
        .all()
    )
    plan_count: dict[int, int] = {}
    plan_name: dict[int, str] = {}
    for menu_id, menu_name, _plan_date in plan_rows:
        plan_count[menu_id] = plan_count.get(menu_id, 0) + 1
        plan_name[menu_id] = menu_name

    log_start = dt.datetime.combine(period_start, dt.time())
    log_end = dt.datetime.combine(period_end, dt.time()) + dt.timedelta(days=1)
    log_filters = [MealLog.eaten_at >= log_start, MealLog.eaten_at < log_end]
    if meal_type is not None:
        log_filters.append(MealLog.meal_type == meal_type)
    if corner_id is not None:
        log_filters.append(MealLog.corner_id == corner_id)
    log_rows = (
        db.query(MealLog.menu_id, MealLog.taste_score).filter(*log_filters).all()
    )
    headcount: dict[int, int] = {}
    scores: dict[int, list[float]] = {}
    for menu_id, taste_score in log_rows:
        if menu_id is None:
            continue
        headcount[menu_id] = headcount.get(menu_id, 0) + 1
        if taste_score is not None:
            scores.setdefault(menu_id, []).append(TASTE_SCORE_POINTS[taste_score])

    # 기준선은 그 기간 전체의 중앙값 — 기존 4분면(aggregation.py)과 같은 방식
    median_plan = median_or_zero([float(c) for c in plan_count.values()])
    satisfaction_values = [
        statistics.fmean(v) for v in scores.values() if v
    ]
    median_satisfaction = median_or_zero(satisfaction_values)

    items = []
    for menu_id, count in plan_count.items():
        menu_scores = scores.get(menu_id, [])
        avg_satisfaction = statistics.fmean(menu_scores) if menu_scores else None
        total_headcount = headcount.get(menu_id, 0)
        action = classify_planning_action(
            count,
            avg_satisfaction,
            len(menu_scores),
            total_headcount,
            median_plan_count=median_plan,
            median_satisfaction=median_satisfaction,
        )
        items.append(
            {
                "menu_id": menu_id,
                "menu_name": plan_name[menu_id],
                "plan_count": count,
                "total_headcount": total_headcount,
                "headcount_per_plan": round(total_headcount / count, 1) if count else 0.0,
                "evaluation_count": len(menu_scores),
                "avg_satisfaction": round(avg_satisfaction, 2) if avg_satisfaction is not None else None,
                "action": action.value,
            }
        )
    items.sort(key=lambda r: (-r["plan_count"], r["menu_name"]))

    # 매칭 진단 — 식단표 MAIN과 취식기록이 실제로 이어졌는지
    planned_ids = set(plan_count)
    logged_ids = {mid for mid in headcount if headcount[mid] > 0}
    plan_only_ids = planned_ids - logged_ids
    log_only_ids = logged_ids - planned_ids
    log_only_names = {
        m.menu_id: m.menu_name
        for m in db.query(MenuMaster).filter(MenuMaster.menu_id.in_(log_only_ids)).all()
    } if log_only_ids else {}

    plan_only = sorted(plan_name[mid] for mid in plan_only_ids)
    log_only = sorted(log_only_names.values())

    # 표기만 달라 갈라진 짝을 미리 짚어준다(2026-08). 담당자가 두 목록을 눈으로
    # 대조해 "연어파피요트"와 "연어 파피요트"를 찾아내야 했다 — 정규화하면 같아지는
    # 이름끼리는 기계가 찾아주는 게 맞다.
    likely_pairs = pair_likely_same_menu(plan_only, log_only)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "median_plan_count": median_plan,
        "median_satisfaction": round(median_satisfaction, 2),
        "items": items,
        "matching": {
            "matched": len(planned_ids & logged_ids),
            # 편성됐는데 취식 0 — "진짜 아무도 안 먹음"과 "메뉴명이 안 맞아
            # 매칭 실패"가 섞여 있으므로 목록째 넘겨 담당자가 판단하게 한다.
            "plan_only": plan_only,
            # 취식은 있는데 그 기간 식단표에 MAIN으로 없는 메뉴
            "log_only": log_only,
            # 양쪽에 있으면서 정규화하면 같아지는 짝 — 이름 표기 차이로 갈라진
            # 것이고, merge_duplicate_menus로 합칠 수 있다.
            "likely_same_menu": likely_pairs,
        },
    }


@router.get("/menu-plan/repertoire")
def menu_plan_repertoire(
    period_start: dt.date,
    period_end: dt.date,
    db: Session = Depends(get_db),
):
    """코너 × 역할(메인/부찬/건강가든)별 레퍼토리 다양성 (2026-08).

    "이 코너는 8개월간 몇 종을 돌렸나, 상위 몇 개에 얼마나 쏠렸나"를 본다.
    `top_share`와 `hhi`를 둘 다 내는 이유는 `menu_plan_analytics`의 docstring 참고.
    """
    rows = (
        db.query(
            CornerMaster.corner_name,
            WeeklyMenuPlan.menu_role,
            MenuMaster.menu_name,
        )
        .join(MenuMaster, WeeklyMenuPlan.menu_id == MenuMaster.menu_id)
        .join(CornerMaster, WeeklyMenuPlan.corner_id == CornerMaster.corner_id)
        .filter(WeeklyMenuPlan.plan_date.between(period_start, period_end))
        .all()
    )
    buckets: dict[tuple[str, str], dict[str, int]] = {}
    for corner_name, menu_role, menu_name in rows:
        role_value = menu_role.value if hasattr(menu_role, "value") else str(menu_role)
        counts = buckets.setdefault((corner_name, role_value), {})
        counts[menu_name] = counts.get(menu_name, 0) + 1

    results = []
    for (corner_name, role_value), counts in buckets.items():
        stats = compute_repertoire(counts)
        results.append(
            {
                "corner_name": corner_name,
                "menu_role": role_value,
                "total_slots": stats.total_slots,
                "unique_menus": stats.unique_menus,
                "top_share": stats.top_share,
                "hhi": stats.hhi,
                "top_menus": [{"menu_name": n, "count": c} for n, c in stats.top_menus],
            }
        )
    results.sort(key=lambda r: (r["corner_name"], r["menu_role"]))
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "items": results,
    }


@router.get("/menu-combinations/spread-ranking")
def menu_combination_spread_ranking(
    period_start: dt.date,
    period_end: dt.date,
    min_day_count: int = 2,
    top_n: int = 10,
    corner_id: int | None = None,
    db: Session = Depends(get_db),
):
    """조합에 따라 만족도 **편차가 큰 메인메뉴**를 먼저 보여준다 (2026-08 요청).

    부찬 조합 비교가 메뉴명 검색으로만 열리다 보니 "뭘 검색해야 하는지"부터
    막힌다는 피드백이 있었다. 편차가 크다 = 부찬을 바꾸면 만족도가 실제로
    움직인다 = 손볼 가치가 있다. 편차가 0에 가까운 메뉴는 뭘 붙여도 결과가
    같으니 볼 필요가 없다.

    `min_day_count` 기본 2: 1일짜리 조합은 그날 컨디션이 그대로 편차가 되어
    랭킹 상위가 전부 우연으로 찬다.
    """
    combos_by_menu = build_side_combos_bulk(db, period_start, period_end, corner_id=corner_id)
    if not combos_by_menu:
        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "corner_id": corner_id,
            "min_day_count": min_day_count,
            "items": [],
        }

    all_menu_ids: set[int] = set(combos_by_menu)
    summaries_by_menu: dict[int, list] = {}
    for main_menu_id, days in combos_by_menu.items():
        summaries = compute_combo_satisfaction_summary(days, min_day_count=min_day_count)
        summaries_by_menu[main_menu_id] = summaries
        for s in summaries:
            all_menu_ids.update(s.side_menu_ids)

    menu_names = {
        m.menu_id: m.menu_name
        for m in db.query(MenuMaster).filter(MenuMaster.menu_id.in_(all_menu_ids)).all()
    }

    def _combo_payload(summary) -> dict:
        return {
            "sides": [menu_names.get(sid) for sid in sorted(summary.side_menu_ids)],
            "avg_satisfaction": summary.avg_satisfaction,
            "day_count": summary.day_count,
        }

    items = []
    for main_menu_id, summaries in summaries_by_menu.items():
        spread = compute_combo_spread(summaries)
        if spread is None:
            continue  # 평가 있는 조합이 1개 이하 — 비교 자체가 불가능
        # compute_combo_satisfaction_summary가 이미 만족도 내림차순(평가 없는
        # 조합은 맨 뒤)으로 정렬해 두므로, 평가 있는 것 중 처음/마지막이 최고/최저다.
        scored = [s for s in summaries if s.avg_satisfaction is not None]
        items.append(
            {
                "menu_id": main_menu_id,
                "menu_name": menu_names.get(main_menu_id),
                "combo_count": len(summaries),
                "spread": round(spread, 2),
                "best": _combo_payload(scored[0]),
                "worst": _combo_payload(scored[-1]),
            }
        )

    items.sort(key=lambda r: -r["spread"])
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "corner_id": corner_id,
        "min_day_count": min_day_count,
        "items": items[:top_n],
    }


@router.get("/menu-combinations/{menu_name}")
def menu_side_combinations(
    menu_name: str,
    period_start: dt.date,
    period_end: dt.date,
    corner_id: int | None = None,
    db: Session = Depends(get_db),
):
    """이 메뉴가 메인(주찬)으로 나온 날짜들을 부찬 조합별로 묶어 만족도를
    비교한다. 같은 메인메뉴는 항상 같은 부찬을 받는다는 전제(2026-07 확인)로
    날짜 단위 비교를 쓴다 — meal_log는 개인이 어떤 부찬을 골랐는지 모른다.
    """
    menu = db.query(MenuMaster).filter_by(menu_name=menu_name).one_or_none()
    if menu is None:
        raise HTTPException(status_code=404, detail=f"'{menu_name}' 메뉴를 찾을 수 없습니다")

    days = build_side_combos_for_main_menu(
        db, menu.menu_id, period_start, period_end, corner_id=corner_id
    )
    summaries = compute_combo_satisfaction_summary(days)

    all_menu_ids = {menu.menu_id}
    for s in summaries:
        all_menu_ids.update(s.side_menu_ids)
    menus = db.query(MenuMaster).filter(MenuMaster.menu_id.in_(all_menu_ids)).all()
    menu_names = {m.menu_id: m.menu_name for m in menus}
    food_vectors = {m.menu_id: [float(x) for x in m.food_vector] for m in menus if m.food_vector is not None}

    return {
        "menu_id": menu.menu_id,
        "menu_name": menu.menu_name,
        "corner_id": corner_id,
        "combos": [
            {
                "sides": [menu_names.get(sid) for sid in sorted(s.side_menu_ids)],
                "day_count": s.day_count,
                "avg_satisfaction": s.avg_satisfaction,
                "avg_headcount": round(s.avg_headcount, 1),
                "nutrition_profile": compute_combo_nutrition_profile(
                    [menu.menu_id, *s.side_menu_ids], food_vectors
                ),
            }
            for s in summaries
        ],
    }


@router.get("/menu-pairs/top")
def top_menu_pairs(
    period_start: dt.date,
    period_end: dt.date,
    min_co_count: int = 3,
    top_n: int = 10,
    db: Session = Depends(get_db),
):
    """PRD 6.2 확장: 코너 구분 없이 전체 인원 기준 가장 흔한 메뉴 동반 선택 쌍.

    코너별 코어층 비교(`/corners/{corner_id}/core-layer-menu-pairs`)는 특정
    코너의 반복 이용자로 범위를 좁히지만, 이건 전체 인원·전체 메뉴를 대상으로
    구한다 — 같은 `compute_top_menu_pairs`를 코너로 나누지 않고 그대로 호출한다.
    """
    employee_menus = build_employee_menu_sets(db, period_start, period_end)
    pairs = compute_top_menu_pairs(employee_menus, min_co_count=min_co_count, top_n=top_n)
    food_vector_by_name = {
        m.menu_name: [float(x) for x in m.food_vector]
        for m in db.query(MenuMaster).all()
        if m.food_vector is not None
    }
    return [
        {
            "menu_a": p.menu_a,
            "menu_b": p.menu_b,
            "co_count": p.co_count,
            "lift": p.lift,
            "is_obvious_pair": is_obvious_pair(food_vector_by_name.get(p.menu_a), food_vector_by_name.get(p.menu_b)),
        }
        for p in pairs
    ]
