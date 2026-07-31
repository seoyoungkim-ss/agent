"""PRD 3.1/3.2: 평일 / 주말+공휴일 / 패밀리데이 분류 서비스.

근로자의 날, 대체공휴일을 포함해 holiday_calendar 테이블에 등록된 날짜와
토/일요일을 모두 "휴일"로 취급한다. 이 분류는 홈/분석/시뮬레이션 화면의
공통 필터(평일 vs 주말+공휴일 vs 패밀리데이)에서 그대로 재사용한다.

패밀리데이(2026-07 추가): 매월 21일이 속한 주의 금요일 — 출근이 자율인
날로, 평일과 식수를 그대로 비교하면 왜곡이 생긴다는 실사용 피드백에 따라
별도 분류로 뺐다. 공휴일과 겹치면 공휴일이 우선(실제 휴무가 자율출근보다
상위 개념).
"""

import datetime as dt
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.master import HolidayCalendar

_WEEKEND_ISOWEEKDAYS = {6, 7}  # ISO: 월=1 ... 토=6, 일=7
_FAMILY_DAY_ANCHOR_DAY = 21  # "21일이 있는 주"의 기준 날짜
_FAMILY_DAY_ISOWEEKDAY = 5  # 금요일


class DayClassification(str, Enum):
    WEEKDAY = "평일"
    HOLIDAY = "주말+공휴일"
    FAMILY_DAY = "패밀리데이"


def is_weekend(target_date: dt.date) -> bool:
    return target_date.isoweekday() in _WEEKEND_ISOWEEKDAYS


def family_day_of_month(year: int, month: int) -> dt.date:
    """그 달의 21일이 속한 주(월~일)의 금요일을 반환한다(순수함수)."""
    anchor = dt.date(year, month, _FAMILY_DAY_ANCHOR_DAY)
    return anchor + dt.timedelta(days=_FAMILY_DAY_ISOWEEKDAY - anchor.isoweekday())


def is_family_day(target_date: dt.date) -> bool:
    return target_date == family_day_of_month(target_date.year, target_date.month)


def family_day_dates_in_range(start: dt.date, end: dt.date) -> set[dt.date]:
    """[start, end] 구간과 겹치는 달들의 패밀리데이만 모아 반환한다(순수함수)."""
    dates: set[dt.date] = set()
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        candidate = family_day_of_month(year, month)
        if start <= candidate <= end:
            dates.add(candidate)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return dates


class HolidayService:
    """holiday_calendar를 메모리에 캐싱해 날짜 분류를 빠르게 반복 조회한다.

    데이터가 계속 누적되는 서비스 특성상, 배치/분석 작업에서 같은 기간을
    반복 조회하는 일이 많아 세션 단위로 날짜 집합을 한 번만 로드한다.
    """

    def __init__(self, db: Session):
        self._db = db
        self._holiday_dates: set[dt.date] | None = None

    def _load(self) -> set[dt.date]:
        if self._holiday_dates is None:
            rows = self._db.execute(select(HolidayCalendar.calendar_date)).scalars().all()
            self._holiday_dates = set(rows)
        return self._holiday_dates

    def is_holiday(self, target_date: dt.date) -> bool:
        return is_weekend(target_date) or target_date in self._load()

    def classify(self, target_date: dt.date) -> DayClassification:
        if self.is_holiday(target_date):
            return DayClassification.HOLIDAY
        if is_family_day(target_date):
            return DayClassification.FAMILY_DAY
        return DayClassification.WEEKDAY

    def classify_range(self, start: dt.date, end: dt.date) -> dict[dt.date, DayClassification]:
        result: dict[dt.date, DayClassification] = {}
        current = start
        while current <= end:
            result[current] = self.classify(current)
            current += dt.timedelta(days=1)
        return result
