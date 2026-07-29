"""배치 집계 서비스 — APScheduler(app/scheduler.py)가 주기적으로 호출한다.

meal_log(원본 로그)는 건드리지 않고, 그로부터 daily_corner_stats /
daily_division_stats / menu_performance_stats를 다시 계산해 채운다(PRD 4.3:
집계 테이블은 배치 재계산 방식).
"""

import datetime as dt
import statistics

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.enums import TASTE_SCORE_POINTS, Division, MealType
from app.models.logs import MealLog
from app.models.master import EmployeeMaster, MenuMaster
from app.models.stats import DailyCornerStats, DailyDivisionStats, MenuPerformanceStats
from app.services.holidays import HolidayService
from app.services.menu_performance import (
    DeclineDiagnosis,
    TrendDirection,
    classify_menu_quadrant,
    compute_menu_frequency,
    compute_menu_score,
    compute_share_of_traffic,
    diagnose_headcount_decline,
)

_FLAT_TOLERANCE = 0.05  # ±5% 이내 변화는 "유지"로 취급

# 테이크아웃 특성상(세부 메뉴를 정확히 못 남김) 4분면 비교에 안 맞는 플레이스홀더성
# 메뉴명 — 다른 메뉴들의 수요/만족도 중앙값(4분면 임계값)이 왜곡되지 않도록 집계
# 자체에서 제외한다(2026-07 실사용 확인).
EXCLUDED_QUADRANT_MENU_NAMES = {"선택형 Take out", "(포장)메디쏠라"}


def _parse_time(value: str) -> dt.time:
    return dt.datetime.strptime(value, "%H:%M:%S").time()


def aggregate_daily_stats(db: Session, target_date: dt.date, settings: Settings | None = None) -> None:
    """PRD 6.2: 특정 날짜의 코너별/구분별 일일 통계를 다시 계산해 upsert한다."""
    settings = settings or get_settings()
    holiday_svc = HolidayService(db)
    is_holiday = holiday_svc.is_holiday(target_date)

    day_start = dt.datetime.combine(target_date, dt.time())
    day_end = day_start + dt.timedelta(days=1)
    peak_start = dt.datetime.combine(target_date, _parse_time(settings.peak_time_start))
    peak_end = dt.datetime.combine(target_date, _parse_time(settings.peak_time_end))
    peak_minutes = max((peak_end - peak_start).total_seconds() / 60, 1)

    logs = (
        db.query(MealLog)
        .filter(MealLog.eaten_at >= day_start, MealLog.eaten_at < day_end)
        .all()
    )

    # ---- 코너별 ----
    by_corner: dict[tuple[int, MealType], list[MealLog]] = {}
    for log in logs:
        by_corner.setdefault((log.corner_id, log.meal_type), []).append(log)

    for (corner_id, meal_type), rows in by_corner.items():
        scores = [TASTE_SCORE_POINTS[r.taste_score] for r in rows if r.taste_score is not None]
        avg_score = statistics.fmean(scores) if scores else None
        peak_count = sum(1 for r in rows if peak_start <= r.eaten_at < peak_end)
        throughput = peak_count / peak_minutes if peak_count else 0.0

        existing = (
            db.query(DailyCornerStats)
            .filter_by(stat_date=target_date, corner_id=corner_id, meal_type=meal_type)
            .one_or_none()
        )
        if existing is None:
            existing = DailyCornerStats(stat_date=target_date, corner_id=corner_id, meal_type=meal_type)
            db.add(existing)
        existing.headcount = len(rows)
        existing.avg_taste_score = avg_score
        existing.peak_throughput_per_min = throughput
        existing.is_holiday = is_holiday

    # ---- 본사/계열사/기타 구분별 ----
    employee_division = dict(db.query(EmployeeMaster.employee_id, EmployeeMaster.division).all())
    by_division: dict[tuple[Division, MealType], int] = {}
    for log in logs:
        division = employee_division.get(log.employee_id, Division.OTHER)
        key = (division, log.meal_type)
        by_division[key] = by_division.get(key, 0) + 1

    for (division, meal_type), headcount in by_division.items():
        existing = (
            db.query(DailyDivisionStats)
            .filter_by(stat_date=target_date, division=division, meal_type=meal_type)
            .one_or_none()
        )
        if existing is None:
            existing = DailyDivisionStats(stat_date=target_date, division=division, meal_type=meal_type)
            db.add(existing)
        existing.headcount = headcount
        existing.is_holiday = is_holiday

    db.commit()


def aggregate_menu_performance(
    db: Session,
    period_start: dt.date,
    period_end: dt.date,
    settings: Settings | None = None,
) -> int:
    """PRD 6.3: 기간 내 menu_performance_stats를 다시 계산한다. 반환값은 갱신된 메뉴 수."""
    settings = settings or get_settings()
    period_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    period_start_dt = dt.datetime.combine(period_start, dt.time())

    excluded_menu_ids = {
        menu_id
        for (menu_id,) in db.query(MenuMaster.menu_id).filter(
            MenuMaster.menu_name.in_(EXCLUDED_QUADRANT_MENU_NAMES)
        )
    }

    query = db.query(MealLog).filter(
        MealLog.eaten_at >= period_start_dt,
        MealLog.eaten_at < period_end_exclusive,
        MealLog.menu_id.isnot(None),
    )
    if excluded_menu_ids:
        query = query.filter(MealLog.menu_id.notin_(excluded_menu_ids))
    logs = query.all()
    if not logs:
        return 0

    total_headcount_all = len(logs)
    all_scores = [TASTE_SCORE_POINTS[l.taste_score] for l in logs if l.taste_score is not None]
    global_avg_score = statistics.fmean(all_scores) if all_scores else 3.0

    by_menu: dict[int, list[MealLog]] = {}
    for log in logs:
        by_menu.setdefault(log.menu_id, []).append(log)

    # 1차 패스: 4분면 기준선(중앙값) 계산을 위해 메뉴별 지표를 먼저 모은다.
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
        prelim[menu_id] = {
            "rows": rows,
            "score_result": score_result,
            "freq": freq,
            "demand": demand,
        }

    demand_values = [v["demand"] for v in prelim.values()]
    score_values = [
        v["score_result"].adjusted_score
        for v in prelim.values()
        if v["score_result"].adjusted_score is not None
    ]
    demand_threshold = statistics.median(demand_values) if demand_values else 0.0
    score_threshold = statistics.median(score_values) if score_values else global_avg_score

    for menu_id, data in prelim.items():
        score_result = data["score_result"]
        freq = data["freq"]
        share = compute_share_of_traffic(freq.total_headcount, total_headcount_all)
        quadrant = classify_menu_quadrant(
            demand=data["demand"],
            satisfaction=score_result.adjusted_score or global_avg_score,
            demand_threshold=demand_threshold,
            satisfaction_threshold=score_threshold,
            evaluation_count=score_result.evaluation_count,
            low_sample_threshold=settings.menu_score_low_sample_threshold,
        )

        existing = (
            db.query(MenuPerformanceStats)
            .filter_by(period_start=period_start, period_end=period_end, menu_id=menu_id)
            .one_or_none()
        )
        if existing is None:
            existing = MenuPerformanceStats(
                period_start=period_start, period_end=period_end, menu_id=menu_id
            )
            db.add(existing)
        existing.appearance_count = freq.appearance_count
        existing.total_headcount = freq.total_headcount
        existing.evaluation_count = freq.evaluation_count
        existing.evaluation_rate = freq.evaluation_rate
        existing.raw_score = score_result.raw_score
        existing.adjusted_score = score_result.adjusted_score
        existing.share_of_traffic = share
        existing.quadrant_label = quadrant

    db.commit()
    return len(prelim)


def _trend(previous: float | None, current: float | None) -> TrendDirection:
    if previous is None or current is None or previous == 0:
        return TrendDirection.FLAT
    change = (current - previous) / previous
    if change <= -_FLAT_TOLERANCE:
        return TrendDirection.DOWN
    if change >= _FLAT_TOLERANCE:
        return TrendDirection.UP
    return TrendDirection.FLAT


def diagnose_menu_decline(
    db: Session, menu_id: int, recent: tuple[dt.date, dt.date], prior: tuple[dt.date, dt.date]
) -> DeclineDiagnosis | None:
    """PRD 6.3.3: 두 기간(최근 vs 이전)의 menu_performance_stats를 비교해 하락 원인을 진단한다."""
    recent_stat = (
        db.query(MenuPerformanceStats)
        .filter_by(period_start=recent[0], period_end=recent[1], menu_id=menu_id)
        .one_or_none()
    )
    prior_stat = (
        db.query(MenuPerformanceStats)
        .filter_by(period_start=prior[0], period_end=prior[1], menu_id=menu_id)
        .one_or_none()
    )
    if recent_stat is None or prior_stat is None:
        return None

    share_trend = _trend(prior_stat.share_of_traffic, recent_stat.share_of_traffic)
    satisfaction_trend = _trend(prior_stat.adjusted_score, recent_stat.adjusted_score)
    return diagnose_headcount_decline(share_trend, satisfaction_trend)
