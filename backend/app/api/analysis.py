import datetime as dt
import statistics
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.enums import FoodVectorSource
from app.models.logs import MealLog
from app.models.master import CornerMaster, MenuMaster
from app.models.stats import (
    DailyCornerStats,
    DailyDivisionStats,
    EmployeeTasteProfile,
    MenuPerformanceStats,
    TasteCluster,
)
from app.services.aggregation import aggregate_daily_stats, aggregate_menu_performance, diagnose_menu_decline
from app.services.corner_core_layer import build_employee_corner_counts, classify_corner_core_layer
from app.services.food_vector import FOOD_VECTOR_DIMENSIONS
from app.services.food_vector_tagging import run_llm_food_vector_tagging
from app.services.holidays import DayClassification
from app.services.llm_client import InternalLLMClient
from app.services.master_data import TAKE_OUT_CORNER_NAME
from app.services.menu_affinity import (
    build_employee_menu_sets,
    compute_menu_affinity,
    compute_top_menu_pairs,
)
from app.services.taste_clustering import compute_taste_clusters
from app.services.taste_profile import compute_employee_taste_profiles

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
    """
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
    return corner_id_by_menu


@router.get("/divisions")
def division_analysis(
    period_start: dt.date,
    period_end: dt.date,
    granularity: Literal["daily", "weekly", "monthly"] = "daily",
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일"),
    db: Session = Depends(get_db),
):
    """PRD 6.1: 본사/계열사/기타 구분 일간/주간/월간 식수."""
    query = db.query(DailyDivisionStats).filter(
        DailyDivisionStats.stat_date.between(period_start, period_end)
    )
    if classification == DayClassification.WEEKDAY.value:
        query = query.filter(DailyDivisionStats.is_holiday.is_(False))
    elif classification == DayClassification.HOLIDAY.value:
        query = query.filter(DailyDivisionStats.is_holiday.is_(True))

    totals: dict[tuple[str, str], int] = {}
    for row in query.all():
        key = (_period_bucket(row.stat_date, granularity), row.division.value)
        totals[key] = totals.get(key, 0) + row.headcount

    return [
        {"period": period, "division": division, "headcount": headcount}
        for (period, division), headcount in sorted(totals.items())
    ]


def _load_corner_stats(
    db: Session, period_start: dt.date, period_end: dt.date, classification: str | None
) -> tuple[list[DailyCornerStats], dict[int, CornerMaster]]:
    query = db.query(DailyCornerStats).filter(DailyCornerStats.stat_date.between(period_start, period_end))
    if classification == DayClassification.WEEKDAY.value:
        query = query.filter(DailyCornerStats.is_holiday.is_(False))
    elif classification == DayClassification.HOLIDAY.value:
        query = query.filter(DailyCornerStats.is_holiday.is_(True))
    corners = {c.corner_id: c for c in db.query(CornerMaster).all()}
    return query.all(), corners


@router.get("/corners")
def corner_analysis(
    period_start: dt.date,
    period_end: dt.date,
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일"),
    exclude_take_out: bool = Query(
        default=False, description="Take Out 코너 제외 — 착석 취식이 아니라 혼잡도/만족도 분석에 안 맞음"
    ),
    db: Session = Depends(get_db),
):
    """PRD 6.2: 코너별 이용자 수/만족도/피크타임 서브속도.

    그린미트(다이어트식, 매니아층 전용)는 항상 마지막 행으로 정렬한다 — 코너가
    나오는 화면 어디서든 일반 코너 비교에 섞이지 않도록.
    """
    rows, corners = _load_corner_stats(db, period_start, period_end, classification)

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
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일"),
    exclude_take_out: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """PRD 6.2 확장: 코너별 만족도/피크타임 서브속도(및 식수)의 기간별(일간·주간·월간)
    추이. 홈 화면의 "코너별 주간 식수 추이"는 이 엔드포인트를 daily로 호출한다."""
    rows, corners = _load_corner_stats(db, period_start, period_end, classification)

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

    def _serialize(pairs):
        return [
            {"menu_a": p.menu_a, "menu_b": p.menu_b, "co_count": p.co_count, "lift": p.lift}
            for p in pairs
        ]

    return {
        "corner_id": corner_id,
        "corner_name": corner.corner_name,
        "core_layer": {
            "employee_count": len(core_employee_ids),
            "min_visit_count": min_visit_count,
            "min_share": min_share,
            "top_pairs": _serialize(
                compute_top_menu_pairs(core_menus, min_co_count=min_co_count, top_n=top_n)
            ),
        },
        "non_core": {
            "employee_count": len(non_core_employee_ids),
            "top_pairs": _serialize(
                compute_top_menu_pairs(non_core_menus, min_co_count=min_co_count, top_n=top_n)
            ),
        },
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
        }
        for r in rows
    ]


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


@router.post("/menus/tag-with-llm")
async def tag_menus_with_llm(db: Session = Depends(get_db)):
    """PRD 6.1: 규칙 기반으로 태깅 못 한(food_vector NULL) 메뉴를 사내 LLM으로 보강한다."""
    client = InternalLLMClient(get_settings())
    tagged = await run_llm_food_vector_tagging(db, client)
    return {"tagged_menus": tagged}


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
    return [{"menu_a": p.menu_a, "menu_b": p.menu_b, "co_count": p.co_count, "lift": p.lift} for p in pairs]
