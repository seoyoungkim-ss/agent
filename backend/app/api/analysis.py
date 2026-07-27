import datetime as dt
import statistics

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.master import CornerMaster, MenuMaster
from app.models.stats import DailyCornerStats, EmployeeTasteProfile, MenuPerformanceStats
from app.services.aggregation import aggregate_menu_performance, diagnose_menu_decline
from app.services.food_vector import FOOD_VECTOR_DIMENSIONS
from app.services.holidays import DayClassification
from app.services.taste_profile import compute_employee_taste_profiles

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/corners")
def corner_analysis(
    period_start: dt.date,
    period_end: dt.date,
    classification: str | None = Query(default=None, description="평일 | 주말+공휴일"),
    db: Session = Depends(get_db),
):
    """PRD 6.2: 코너별 이용자 수/만족도/피크타임 서브속도."""
    query = db.query(DailyCornerStats).filter(DailyCornerStats.stat_date.between(period_start, period_end))
    if classification == DayClassification.WEEKDAY.value:
        query = query.filter(DailyCornerStats.is_holiday.is_(False))
    elif classification == DayClassification.HOLIDAY.value:
        query = query.filter(DailyCornerStats.is_holiday.is_(True))
    rows = query.all()

    corners = {c.corner_id: c for c in db.query(CornerMaster).all()}
    by_corner: dict[int, list[DailyCornerStats]] = {}
    for row in rows:
        by_corner.setdefault(row.corner_id, []).append(row)

    result = []
    for corner_id, stats in by_corner.items():
        corner = corners.get(corner_id)
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
    return result


@router.get("/menu-performance")
def menu_performance(period_start: dt.date, period_end: dt.date, db: Session = Depends(get_db)):
    """PRD 6.3: 메뉴별 성과 (4분면 라벨 포함). 사전에 recompute가 호출돼 있어야 한다."""
    rows = (
        db.query(MenuPerformanceStats)
        .filter_by(period_start=period_start, period_end=period_end)
        .all()
    )
    menus = {m.menu_id: m.menu_name for m in db.query(MenuMaster).all()}
    return [
        {
            "menu_id": r.menu_id,
            "menu_name": menus.get(r.menu_id),
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
    return {
        "employee_id": employee_id,
        "profile_vector": list(profile.profile_vector),
        "dimensions": FOOD_VECTOR_DIMENSIONS,
        "sample_size": profile.sample_size,
    }


@router.post("/users/taste-profile/recompute")
def recompute_taste_profiles(db: Session = Depends(get_db)):
    updated = compute_employee_taste_profiles(db)
    return {"updated_employees": updated}
