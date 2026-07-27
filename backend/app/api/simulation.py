import datetime as dt
import statistics
from enum import Enum

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.enums import MealType
from app.models.master import CornerMaster
from app.models.stats import DailyCornerStats
from app.services.holidays import DayClassification, HolidayService

router = APIRouter(prefix="/simulation", tags=["simulation"])

_HISTORY_WINDOW = 8  # 최근 같은 분류(평일/휴일)·식사구분 N회 평균을 baseline으로 사용


class Weather(str, Enum):
    SUNNY = "맑음"
    RAIN = "비"
    HEATWAVE = "폭염"
    COLDWAVE = "한파"


# PRD 7.1: 날씨에 따른 식수 변화 v0 휴리스틱. 실측 데이터가 쌓이면 회귀모델로 교체 필요.
_WEATHER_MULTIPLIER = {
    Weather.SUNNY: 1.00,
    Weather.RAIN: 0.90,
    Weather.HEATWAVE: 0.95,
    Weather.COLDWAVE: 0.95,
}


class WhatIfRequest(BaseModel):
    target_date: dt.date
    meal_type: MealType
    weather: Weather = Weather.SUNNY
    new_menu_corner_id: int | None = None
    has_company_event: bool = False


def _baseline_headcount(db: Session, corner_id: int, meal_type: MealType, is_holiday: bool) -> float:
    history = (
        db.query(DailyCornerStats)
        .filter(
            DailyCornerStats.corner_id == corner_id,
            DailyCornerStats.meal_type == meal_type,
            DailyCornerStats.is_holiday.is_(is_holiday),
        )
        .order_by(DailyCornerStats.stat_date.desc())
        .limit(_HISTORY_WINDOW)
        .all()
    )
    return statistics.fmean([h.headcount for h in history]) if history else 0.0


@router.post("/what-if")
def what_if(payload: WhatIfRequest, db: Session = Depends(get_db)):
    """PRD 7.1: 날씨/신메뉴/사내행사 조건에 따른 메뉴(코너)별 식수 시뮬레이션.

    v0: 최근 동일 평일/휴일 분류 이력 평균에 조건별 배수를 곱하는 휴리스틱이다.
    데이터가 쌓이면 lightgbm 등 회귀모델로 대체하는 것을 목표로 한다(PRD 9.3).
    """
    holiday_svc = HolidayService(db)
    classification = holiday_svc.classify(payload.target_date)
    is_holiday = classification == DayClassification.HOLIDAY

    corners = db.query(CornerMaster).all()
    results = []
    for corner in corners:
        baseline = _baseline_headcount(db, corner.corner_id, payload.meal_type, is_holiday)
        multiplier = _WEATHER_MULTIPLIER[payload.weather]
        if payload.has_company_event:
            multiplier *= 0.90  # 사내 행사가 있으면 카페테리아 이용이 다소 줄어든다는 가정(v0)
        if payload.new_menu_corner_id == corner.corner_id:
            multiplier *= 1.15  # 신메뉴 코너는 관심 증가로 일시적 수요 증가 가정(v0)
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


@router.get("/congestion-forecast")
def congestion_forecast(target_date: dt.date, meal_type: MealType, db: Session = Depends(get_db)):
    """PRD 7.2: 코너별 혼잡도(대기시간) 추정 — 예상 식수 ÷ 최근 서브속도.

    실제 What-if 대체 시뮬레이션(다른 코너 메뉴를 바꾸면 분산되는지)은 이 baseline
    위에서 클라이언트가 시나리오별로 /what-if를 반복 호출해 비교하는 방식으로 v0를
    구성했다. 전용 최적화 로직은 후속 고도화 대상이다.
    """
    holiday_svc = HolidayService(db)
    is_holiday = holiday_svc.is_holiday(target_date)
    corners = db.query(CornerMaster).all()

    forecasts = []
    for corner in corners:
        history = (
            db.query(DailyCornerStats)
            .filter(
                DailyCornerStats.corner_id == corner.corner_id,
                DailyCornerStats.meal_type == meal_type,
                DailyCornerStats.is_holiday.is_(is_holiday),
            )
            .order_by(DailyCornerStats.stat_date.desc())
            .limit(_HISTORY_WINDOW)
            .all()
        )
        baseline = statistics.fmean([h.headcount for h in history]) if history else 0.0
        throughputs = [h.peak_throughput_per_min for h in history if h.peak_throughput_per_min]
        avg_throughput = statistics.fmean(throughputs) if throughputs else None
        expected_wait_minutes = (
            round(baseline / avg_throughput, 1) if avg_throughput and avg_throughput > 0 else None
        )
        forecasts.append(
            {
                "corner_id": corner.corner_id,
                "corner_name": corner.corner_name,
                "predicted_headcount": round(baseline, 1),
                "avg_peak_throughput_per_min": avg_throughput,
                "expected_wait_minutes": expected_wait_minutes,
            }
        )

    return {"target_date": target_date.isoformat(), "meal_type": meal_type.value, "corners": forecasts}
