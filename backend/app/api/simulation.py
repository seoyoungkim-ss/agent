import datetime as dt
import statistics
from enum import Enum

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.analysis import _corner_id_by_menu_from_meal_log
from app.config import get_settings
from app.db import get_db
from app.models.enums import MealType, MenuQuadrant, MenuRole
from app.models.logs import WeeklyMenuPlan
from app.models.master import CornerMaster
from app.models.stats import DailyCornerStats, MenuPerformanceStats
from app.services.corner_aliases import corner_display_sort_key
from app.services.holidays import DayClassification, HolidayAdjacency, HolidayService, is_family_day
from app.services.menu_throughput import build_corner_daily_peak_share, compute_peak_share_ratio, window_minutes
from app.services.weekly_menu_prediction import compute_expected_wait_minutes

router = APIRouter(prefix="/simulation", tags=["simulation"])

_HISTORY_WINDOW = 8  # 최근 같은 분류(평일/휴일/패밀리데이)·식사구분 N회 평균을 baseline으로 사용
_WEEKDAY_HISTORY_SCAN_LIMIT = _HISTORY_WINDOW * 4  # 평일 풀에서 패밀리데이를 걸러내야 해서 조금 더 넉넉히 조회
_FAMILY_DAY_HISTORY_SCAN_LIMIT = 400  # 패밀리데이는 월 1회뿐이라 _HISTORY_WINDOW개를 모으려면 훨씬 넓게 훑어야 함
_PEAK_SHARE_WINDOW_DAYS = 60  # peak_share_ratio 실측용 조회 기간(meal_log 날짜 범위)

# PRD 7.1 신메뉴 배수의 v0 임의값(기존 1.15)을, 이미 성과 데이터가 있는 계획 메뉴는
# 4분면(quadrant)에 따라 더 구체적으로 조정한다 — 표본부족(신메뉴라 데이터가 아직
# 없는 경우)은 기존 신메뉴 가정(1.15)을 그대로 쓴다.
_MENU_QUADRANT_MULTIPLIER = {
    MenuQuadrant.POPULAR: 1.20,
    MenuQuadrant.HIDDEN_GEM: 1.10,
    MenuQuadrant.NEEDS_IMPROVEMENT: 1.05,
    MenuQuadrant.REMOVAL_CANDIDATE: 1.00,
    MenuQuadrant.LOW_SAMPLE: 1.15,
}
_DEFAULT_NEW_MENU_MULTIPLIER = 1.15  # 성과 데이터가 아예 없는 메뉴(진짜 신메뉴)


def _planned_main_menu_id(
    db: Session, corner_id: int, meal_type: MealType, target_date: dt.date
) -> int | None:
    """그 날짜·코너·식사구분에 weekly_menu_plan으로 계획된 메인 메뉴 — 미입력이면
    None(폴백은 호출부가 처리, 32절 "meal_log 우선, weekly_menu_plan은 있으면
    보강" 원칙과 동일).

    예측 경로가 슬롯마다 전 코너를 훑어 같은 (코너, 끼니, 날짜)를 반복 조회하므로
    요청 단위로 캐시한다(2026-08 성능 조사)."""
    cache = db.info.setdefault("_planned_main_menu_cache", {})
    cache_key = (corner_id, meal_type, target_date)
    if cache_key in cache:
        return cache[cache_key]
    row = (
        db.query(WeeklyMenuPlan.menu_id)
        .filter(
            WeeklyMenuPlan.corner_id == corner_id,
            WeeklyMenuPlan.meal_type == meal_type,
            WeeklyMenuPlan.plan_date == target_date,
            WeeklyMenuPlan.menu_role == MenuRole.MAIN,
        )
        .first()
    )
    cache[cache_key] = row[0] if row else None
    return cache[cache_key]


def _menu_popularity_multiplier(db: Session, corner_id: int, menu_id: int) -> float | None:
    """그 메뉴의 최근 share_of_traffic이 코너 평균 대비 얼마나 높은지 배수로
    돌려준다 — 성과 데이터가 없으면(신메뉴 등) None.

    같은 (코너, 메뉴)를 슬롯·날짜마다 반복 조회하므로 요청 단위로 캐시한다."""
    pop_cache = db.info.setdefault("_menu_popularity_cache", {})
    pop_key = (corner_id, menu_id)
    if pop_key in pop_cache:
        return pop_cache[pop_key]

    def _compute() -> float | None:
        menu_stats = (
            db.query(MenuPerformanceStats)
            .filter_by(menu_id=menu_id)
            .order_by(MenuPerformanceStats.period_end.desc())
            .first()
        )
        if menu_stats is None or menu_stats.share_of_traffic is None:
            return None

        corner_id_by_menu = _corner_id_by_menu_from_meal_log(db, menu_stats.period_start, menu_stats.period_end)
        corner_menu_ids = {m for m, c in corner_id_by_menu.items() if c == corner_id}
        if not corner_menu_ids:
            return None
        corner_shares = [
            r.share_of_traffic
            for r in db.query(MenuPerformanceStats)
            .filter(
                MenuPerformanceStats.menu_id.in_(corner_menu_ids),
                MenuPerformanceStats.period_start == menu_stats.period_start,
                MenuPerformanceStats.period_end == menu_stats.period_end,
            )
            .all()
            if r.share_of_traffic is not None
        ]
        corner_avg_share = statistics.fmean(corner_shares) if corner_shares else 0.0
        if corner_avg_share <= 0:
            return None
        return menu_stats.share_of_traffic / corner_avg_share

    pop_cache[pop_key] = _compute()
    return pop_cache[pop_key]


class Weather(str, Enum):
    SUNNY = "맑음"
    CLOUDY = "흐림"
    RAIN = "비"
    SNOW = "눈"
    HEATWAVE = "폭염"
    COLDWAVE = "한파"


# PRD 7.1: 날씨에 따른 식수 변화 v0 휴리스틱. 실측 데이터가 쌓이면 회귀모델로 교체 필요.
# 흐림/눈(§84, 2026-08)도 방향성만 맞춘 v0 값, 실측 근거 없음 — 표본이 쌓이면 보정 필요.
# 흐림은 맑음과 비의 중간(아직 비가 안 와 이동은 자유롭지만 나들이·외부식당 유인이
# 살짝 줄어든다는 가정), 눈은 비보다 낮게(적설로 통근이 비보다 더 지연되고 재택/
# 단축근무가 걸리는 경우도 있어 감소폭이 크다고 봤다).
_WEATHER_MULTIPLIER = {
    Weather.SUNNY: 1.00,
    Weather.CLOUDY: 0.97,
    Weather.RAIN: 0.90,
    Weather.SNOW: 0.85,
    Weather.HEATWAVE: 0.95,
    Weather.COLDWAVE: 0.95,
}

# ⚠️ 연휴 전후 배수도 _WEATHER_MULTIPLIER와 같은 **v0 가정치**다(실측 근거 없음,
# 2026-08). 연휴 앞뒤로 휴가를 붙여 쓰는 인원이 있어 식수가 줄어든다는 전제이고,
# 연휴 전(미리 빠짐)이 연휴 후보다 감소폭이 크다고 봤다. 연휴 표본이 몇 번 쌓이면
# 실제 식수와 대조해 반드시 보정해야 한다 — 지금은 방향성만 맞춘 값이다.
_HOLIDAY_ADJACENCY_MULTIPLIER = {
    HolidayAdjacency.BEFORE_LONG_BREAK: 0.85,
    HolidayAdjacency.AFTER_LONG_BREAK: 0.90,
    HolidayAdjacency.NONE: 1.00,
}


class WhatIfRequest(BaseModel):
    target_date: dt.date
    meal_type: MealType
    weather: Weather = Weather.SUNNY
    new_menu_corner_id: int | None = None
    # 이미 성과 데이터가 있는(과거에 한 번이라도 나온) 계획 메뉴 — 있으면 4분면
    # 기준으로 더 구체적인 배수를 쓴다. 성과 데이터가 없으면(진짜 신메뉴)
    # new_menu_corner_id와 동일하게 기본 배수(1.15)로 처리한다.
    planned_menu_id: int | None = None
    has_company_event: bool = False


def _fetch_classification_history(
    db: Session, corner_id: int, meal_type: MealType, classification: DayClassification
) -> list[DailyCornerStats]:
    """최근 같은 분류(평일/주말+공휴일/패밀리데이)의 daily_corner_stats 최대 _HISTORY_WINDOW개.

    is_holiday 컬럼은 boolean이라 패밀리데이를 구분 못한다 — "평일"/"패밀리데이"
    둘 다 is_holiday=False 풀에서 넉넉히 가져온 뒤 Python에서 is_family_day로
    골라낸다(패밀리데이는 월 1회뿐이라 스캔 범위를 훨씬 넓게 잡음, 평일은
    패밀리데이만 제외하면 되니 조금만 더 넓게 잡음).
    """
    if classification == DayClassification.HOLIDAY:
        return (
            db.query(DailyCornerStats)
            .filter(
                DailyCornerStats.corner_id == corner_id,
                DailyCornerStats.meal_type == meal_type,
                DailyCornerStats.is_holiday.is_(True),
            )
            .order_by(DailyCornerStats.stat_date.desc())
            .limit(_HISTORY_WINDOW)
            .all()
        )

    is_family = classification == DayClassification.FAMILY_DAY
    scan_limit = _FAMILY_DAY_HISTORY_SCAN_LIMIT if is_family else _WEEKDAY_HISTORY_SCAN_LIMIT
    candidates = (
        db.query(DailyCornerStats)
        .filter(
            DailyCornerStats.corner_id == corner_id,
            DailyCornerStats.meal_type == meal_type,
            DailyCornerStats.is_holiday.is_(False),
        )
        .order_by(DailyCornerStats.stat_date.desc())
        .limit(scan_limit)
        .all()
    )
    if is_family:
        return [h for h in candidates if is_family_day(h.stat_date)][:_HISTORY_WINDOW]
    return [h for h in candidates if not is_family_day(h.stat_date)][:_HISTORY_WINDOW]


def _baseline_headcount(db: Session, corner_id: int, meal_type: MealType, classification: DayClassification) -> float:
    """예측 경로가 슬롯·날짜마다 같은 (코너, 끼니, 분류)로 반복 호출하므로
    요청 단위로 캐시한다(2026-08 성능 조사)."""
    cache = db.info.setdefault("_baseline_headcount_cache", {})
    cache_key = (corner_id, meal_type, classification)
    if cache_key in cache:
        return cache[cache_key]
    history = _fetch_classification_history(db, corner_id, meal_type, classification)
    value = statistics.fmean([h.headcount for h in history]) if history else 0.0
    cache[cache_key] = value
    return value


@router.post("/what-if")
def what_if(payload: WhatIfRequest, db: Session = Depends(get_db)):
    """PRD 7.1: 날씨/신메뉴/사내행사 조건에 따른 메뉴(코너)별 식수 시뮬레이션.

    v0: 최근 동일 평일/휴일 분류 이력 평균에 조건별 배수를 곱하는 휴리스틱이다.
    데이터가 쌓이면 lightgbm 등 회귀모델로 대체하는 것을 목표로 한다(PRD 9.3).
    """
    holiday_svc = HolidayService(db)
    classification = holiday_svc.classify(payload.target_date)

    planned_menu_quadrant: MenuQuadrant | None = None
    if payload.planned_menu_id is not None:
        menu_stats = (
            db.query(MenuPerformanceStats)
            .filter_by(menu_id=payload.planned_menu_id)
            .order_by(MenuPerformanceStats.period_end.desc())
            .first()
        )
        planned_menu_quadrant = menu_stats.quadrant_label if menu_stats else None

    # §91: 코너 고정 순서 적용 — 응답 배열 순서가 그대로 UI 나열 순서로
    # 쓰이는 화면이 있어(예: 코너별 예측 막대그래프) 정렬해서 내려준다.
    corners = sorted(
        db.query(CornerMaster).all(), key=lambda c: corner_display_sort_key(c.corner_id, c.corner_name)
    )
    results = []
    for corner in corners:
        baseline = _baseline_headcount(db, corner.corner_id, payload.meal_type, classification)
        multiplier = _WEATHER_MULTIPLIER[payload.weather]
        if payload.has_company_event:
            multiplier *= 0.90  # 사내 행사가 있으면 카페테리아 이용이 다소 줄어든다는 가정(v0)
        if payload.planned_menu_id is not None and payload.new_menu_corner_id == corner.corner_id:
            # 성과 데이터가 있는 계획 메뉴면 4분면별 배수, 없으면(진짜 신메뉴) 기본값
            multiplier *= _MENU_QUADRANT_MULTIPLIER.get(planned_menu_quadrant, _DEFAULT_NEW_MENU_MULTIPLIER)
        elif payload.new_menu_corner_id == corner.corner_id:
            multiplier *= _DEFAULT_NEW_MENU_MULTIPLIER  # 신메뉴 코너는 관심 증가로 일시적 수요 증가 가정(v0)
        predicted = baseline * multiplier
        results.append(
            {
                "corner_id": corner.corner_id,
                "corner_name": corner.corner_name,
                "baseline_headcount": round(baseline, 1),
                "predicted_headcount": round(predicted, 1),
            }
        )

    return {
        "target_date": payload.target_date.isoformat(),
        "classification": classification.value,
        "corners": results,
        "note": "v0 휴리스틱 예측 — 데이터가 쌓이면 회귀모델(lightgbm)로 고도화 필요",
    }


def _forecast_corners(
    db: Session,
    target_date: dt.date,
    meal_type: MealType,
    holiday_svc: HolidayService,
    *,
    extra_multiplier: float = 1.0,
) -> list[dict]:
    """하루 × 한 끼니의 코너별 혼잡도 예측 — `congestion_forecast`와 주간 래퍼가 공유한다.

    `extra_multiplier`는 날씨·연휴 전후처럼 그날 전체에 공통으로 걸리는 배수다
    (코너별 메뉴 인기도 배수와 곱해진다).
    """
    classification = holiday_svc.classify(target_date)
    # §91: 코너 고정 순서 적용 — 응답 배열 순서가 그대로 UI 나열 순서로
    # 쓰이는 화면이 있어(예: 코너별 예측 막대그래프) 정렬해서 내려준다.
    corners = sorted(
        db.query(CornerMaster).all(), key=lambda c: corner_display_sort_key(c.corner_id, c.corner_name)
    )
    settings = get_settings()
    peak_window_minutes = window_minutes(settings.peak_time_start, settings.peak_time_end)
    meal_window_minutes = window_minutes(settings.meal_period_start, settings.meal_period_end)
    fallback_peak_share_ratio = peak_window_minutes / meal_window_minutes

    peak_share_period_end = target_date - dt.timedelta(days=1)
    peak_share_period_start = peak_share_period_end - dt.timedelta(days=_PEAK_SHARE_WINDOW_DAYS)

    forecasts = []
    for corner in corners:
        history = _fetch_classification_history(db, corner.corner_id, meal_type, classification)
        baseline = statistics.fmean([h.headcount for h in history]) if history else 0.0

        planned_menu_id = _planned_main_menu_id(db, corner.corner_id, meal_type, target_date)
        menu_popularity_multiplier = (
            _menu_popularity_multiplier(db, corner.corner_id, planned_menu_id)
            if planned_menu_id is not None
            else None
        )
        predicted_headcount = (
            baseline * menu_popularity_multiplier if menu_popularity_multiplier else baseline
        ) * extra_multiplier

        throughputs = [h.peak_throughput_per_min for h in history if h.peak_throughput_per_min]
        avg_throughput = statistics.fmean(throughputs) if throughputs else None

        # 혼잡 예상 대기시간 — "예상 식수 전체를 처리하는 데 걸리는 총 시간"이
        # 아니라 "피크타임 처리 용량을 넘는 초과분만 대기로 본다"(2026-07 재설계,
        # weekly_menu_prediction.py와 동일 공식/헬퍼 재사용 — 이 엔드포인트만
        # 옛 공식이 남아있던 걸 여기서 같이 바로잡는다).
        peak_count, meal_count = build_corner_daily_peak_share(
            db, corner.corner_id, peak_share_period_start, peak_share_period_end
        )
        peak_share_ratio = compute_peak_share_ratio(peak_count, meal_count)
        if peak_share_ratio is None:
            peak_share_ratio = fallback_peak_share_ratio
        expected_wait_minutes = compute_expected_wait_minutes(
            predicted_headcount, avg_throughput, peak_share_ratio, peak_window_minutes
        )
        expected_peak_headcount = round(predicted_headcount * peak_share_ratio, 1)

        forecasts.append(
            {
                "corner_id": corner.corner_id,
                "corner_name": corner.corner_name,
                "predicted_headcount": round(predicted_headcount, 1),
                "expected_peak_headcount": expected_peak_headcount,
                "avg_peak_throughput_per_min": avg_throughput,
                "expected_wait_minutes": expected_wait_minutes,
                "planned_menu_id": planned_menu_id,
                "menu_popularity_multiplier": (
                    round(menu_popularity_multiplier, 2) if menu_popularity_multiplier else None
                ),
            }
        )
    return forecasts


@router.get("/congestion-forecast")
def congestion_forecast(target_date: dt.date, meal_type: MealType, db: Session = Depends(get_db)):
    """PRD 7.2: 코너별 혼잡도(대기시간) 추정 — 예상 식수 ÷ 최근 서브속도.

    실제 What-if 대체 시뮬레이션(다른 코너 메뉴를 바꾸면 분산되는지)은 이 baseline
    위에서 클라이언트가 시나리오별로 /what-if를 반복 호출해 비교하는 방식으로 v0를
    구성했다. 전용 최적화 로직은 후속 고도화 대상이다.
    """
    forecasts = _forecast_corners(db, target_date, meal_type, HolidayService(db))
    return {"target_date": target_date.isoformat(), "meal_type": meal_type.value, "corners": forecasts}


@router.get("/congestion-forecast/weekly")
def weekly_congestion_forecast(
    period_start: dt.date,
    period_end: dt.date,
    meal_type: MealType,
    weather: Weather = Weather.SUNNY,
    has_company_event: bool = False,
    db: Session = Depends(get_db),
):
    """현황 화면의 "금주 예상 식수" — 기간 내 날짜별 코너 예측을 한 번에 돌려준다.

    프론트가 날짜마다 `/congestion-forecast`를 반복 호출하면 코너마다 60일치 이력
    조회가 매번 도는 탓에 6~7회만 돌려도 무거워져, 백엔드에서 루프를 돈다
    (`HolidayService`도 한 번만 만들어 휴일 집합 캐시를 재사용).

    **휴일은 건너뛴다** — 식당이 안 여는 날이라 0으로 그리면 추이가 왜곡된다.
    날씨는 기상청 연동이 없어 사용자가 고른 값을 그대로 적용한다(2026-08 결정).
    """
    holiday_svc = HolidayService(db)
    # 사내 행사 배수는 what_if와 같은 값을 쓴다 — 시뮬레이션 탭이 없어지면서
    # 그 화면의 유일한 실질 입력이던 "사내 행사"를 여기로 흡수했다(2026-08).
    weather_multiplier = _WEATHER_MULTIPLIER[weather] * (0.90 if has_company_event else 1.0)

    days = []
    cursor = period_start
    while cursor <= period_end:
        classification = holiday_svc.classify(cursor)
        if classification == DayClassification.HOLIDAY:
            cursor += dt.timedelta(days=1)
            continue
        adjacency = holiday_svc.adjacency(cursor)
        multiplier = weather_multiplier * _HOLIDAY_ADJACENCY_MULTIPLIER[adjacency]
        forecasts = _forecast_corners(db, cursor, meal_type, holiday_svc, extra_multiplier=multiplier)
        days.append(
            {
                "target_date": cursor.isoformat(),
                "classification": classification.value,
                "holiday_adjacency": adjacency.value,
                "applied_multiplier": round(multiplier, 3),
                "total_predicted_headcount": round(sum(c["predicted_headcount"] for c in forecasts), 1),
                "corners": forecasts,
            }
        )
        cursor += dt.timedelta(days=1)

    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "meal_type": meal_type.value,
        "weather": weather.value,
        "has_company_event": has_company_event,
        "days": days,
        "note": "v0 휴리스틱 — 날씨/연휴 전후 배수는 실측 보정 전 가정치입니다.",
    }
