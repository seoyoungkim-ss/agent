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
from app.models.enums import TASTE_SCORE_POINTS, Division, MealType, TasteScore, TrendDirection
from app.models.logs import MealLog
from app.models.master import EmployeeMaster, MenuMaster
from app.models.stats import DailyCornerStats, DailyDivisionStats, MenuPerformanceStats
from app.services.holidays import HolidayService
from app.services.master_data import PLACEHOLDER_MENU_NAMES
from app.services.menu_performance import (
    DeclineDiagnosis,
    classify_menu_loyalty,
    classify_menu_quadrant,
    compute_menu_frequency,
    compute_menu_score,
    compute_share_of_traffic,
    compute_trend,
    diagnose_headcount_decline,
)


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


def compute_menu_satisfaction_trends(
    db: Session,
    *,
    menu_ids: list[int],
    period_end: dt.date,
    settings: Settings,
    meal_type: MealType | None = None,
) -> dict[int, TrendDirection]:
    """PRD 6.3.4 확장(2026-07): menu_id별 최근/직전 menu_trend_window_days일
    만족도 추세 — classify_menu_quadrant가 "직전 대비 하락"도 반영하게 됨.
    호출부가 어떤 period_start/period_end로 불리든 상관없이 항상 period_end
    기준으로 최근/직전 구간을 고정해서 비교한다(패밀리데이처럼 표본이 희소한
    경우와 무관하게 항상 같은 기준). `meal_type`을 주면 그 끼니만 필터링해
    끼니별 라이브 twin(analysis.py::menu_performance_by_meal_type)에서도
    재사용한다.
    """
    if not menu_ids:
        return {}
    window = settings.menu_trend_window_days
    recent_start = period_end - dt.timedelta(days=window - 1)
    prior_start = period_end - dt.timedelta(days=2 * window - 1)

    range_start_dt = dt.datetime.combine(prior_start, dt.time())
    range_end_exclusive = dt.datetime.combine(period_end + dt.timedelta(days=1), dt.time())
    trend_query = db.query(MealLog.menu_id, MealLog.taste_score, MealLog.eaten_at).filter(
        MealLog.menu_id.in_(menu_ids),
        MealLog.eaten_at >= range_start_dt,
        MealLog.eaten_at < range_end_exclusive,
    )
    if meal_type is not None:
        trend_query = trend_query.filter(MealLog.meal_type == meal_type)
    rows = trend_query.all()

    recent_scores: dict[int, list[TasteScore]] = {}
    prior_scores: dict[int, list[TasteScore]] = {}
    for menu_id, taste_score, eaten_at in rows:
        if taste_score is None:
            continue
        bucket = recent_scores if eaten_at.date() >= recent_start else prior_scores
        bucket.setdefault(menu_id, []).append(taste_score)

    trends: dict[int, TrendDirection] = {}
    for menu_id in menu_ids:
        recent = recent_scores.get(menu_id, [])
        prior = prior_scores.get(menu_id, [])
        # 두 구간 중 하나라도 평가가 없으면(표본 희소) 추세를 단정하지 않고
        # "유지"로 본다 — 잘못된 하락 판정을 막는 보수적 기본값.
        if not recent or not prior:
            trends[menu_id] = TrendDirection.FLAT
            continue
        recent_avg = statistics.fmean(TASTE_SCORE_POINTS[s] for s in recent)
        prior_avg = statistics.fmean(TASTE_SCORE_POINTS[s] for s in prior)
        trends[menu_id] = compute_trend(prior_avg, recent_avg)
    return trends


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
            MenuMaster.menu_name.in_(PLACEHOLDER_MENU_NAMES)
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
    employee_menu_counts: dict[str, dict[int, int]] = {}
    for log in logs:
        by_menu.setdefault(log.menu_id, []).append(log)
        # 로열티(그 메뉴가 나올 때마다 챙겨 먹는 고정 고객) 판정용 — 이미 읽어둔
        # logs에서 바로 집계하므로 쿼리를 추가로 안 던진다(2026-07).
        employee_menu_counts.setdefault(log.employee_id, {})
        employee_menu_counts[log.employee_id][log.menu_id] = (
            employee_menu_counts[log.employee_id].get(log.menu_id, 0) + 1
        )

    menu_trend_by_id = compute_menu_satisfaction_trends(
        db, menu_ids=list(by_menu.keys()), period_end=period_end, settings=settings
    )

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

        # §104: 예전엔 (period_start, period_end, menu_id) 정확히 일치해야
        # "기존 행"으로 봤는데, 나이트 배치의 180일 롤링 윈도우는 매일 1일씩
        # 밀려 이 조합이 절대 다시 일치하지 않는다 — 매일 밤 메뉴당 새 행이
        # 쌓여 menu_history()가 "기간이 이상하게 나옴" 버그로 이어졌다
        # (2026-08). menu_id만으로 최근 행을 찾아 갱신한다 — 이 함수의 유일한
        # 활성 writer인 나이트 배치가 메뉴당 최신 스냅샷 하나만 필요로 해서
        # 안전하다(다른 기간의 스냅샷을 별도 보관해야 하는 호출자 없음).
        existing = (
            db.query(MenuPerformanceStats)
            .filter_by(menu_id=menu_id)
            .order_by(MenuPerformanceStats.period_end.desc())
            .first()
        )
        if existing is None:
            existing = MenuPerformanceStats(
                period_start=period_start, period_end=period_end, menu_id=menu_id
            )
            db.add(existing)
        else:
            existing.period_start = period_start
            existing.period_end = period_end
        existing.appearance_count = freq.appearance_count
        existing.total_headcount = freq.total_headcount
        existing.evaluation_count = freq.evaluation_count
        existing.evaluation_rate = freq.evaluation_rate
        existing.raw_score = score_result.raw_score
        existing.adjusted_score = score_result.adjusted_score
        existing.share_of_traffic = share
        existing.quadrant_label = quadrant
        existing.satisfaction_trend = satisfaction_trend
        existing.has_loyal_following = has_loyal_following

    db.commit()
    return len(prelim)


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

    share_trend = compute_trend(prior_stat.share_of_traffic, recent_stat.share_of_traffic)
    satisfaction_trend = compute_trend(prior_stat.adjusted_score, recent_stat.adjusted_score)
    return diagnose_headcount_decline(share_trend, satisfaction_trend)
