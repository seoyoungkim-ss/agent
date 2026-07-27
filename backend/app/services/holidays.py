"""PRD 3.1/3.2: 평일 / 주말+공휴일 분류 서비스.

근로자의 날, 대체공휴일을 포함해 holiday_calendar 테이블에 등록된 날짜와
토/일요일을 모두 "휴일"로 취급한다. 이 분류는 홈/분석/시뮬레이션 화면의
공통 필터(평일 vs 주말+공휴일)에서 그대로 재사용한다.
"""

import datetime as dt
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.master import HolidayCalendar

_WEEKEND_ISOWEEKDAYS = {6, 7}  # ISO: 월=1 ... 토=6, 일=7


class DayClassification(str, Enum):
    WEEKDAY = "평일"
    HOLIDAY = "주말+공휴일"


def is_weekend(target_date: dt.date) -> bool:
    return target_date.isoweekday() in _WEEKEND_ISOWEEKDAYS


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
        return DayClassification.HOLIDAY if self.is_holiday(target_date) else DayClassification.WEEKDAY

    def classify_range(self, start: dt.date, end: dt.date) -> dict[dt.date, DayClassification]:
        result: dict[dt.date, DayClassification] = {}
        current = start
        while current <= end:
            result[current] = self.classify(current)
            current += dt.timedelta(days=1)
        return result
