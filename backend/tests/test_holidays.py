import datetime as dt

from app.models.enums import HolidayType
from app.models.master import HolidayCalendar
from app.services.holidays import DayClassification, HolidayService, is_weekend


def test_is_weekend():
    assert is_weekend(dt.date(2026, 7, 25))  # 토요일
    assert is_weekend(dt.date(2026, 7, 26))  # 일요일
    assert not is_weekend(dt.date(2026, 7, 27))  # 월요일


def test_weekday_without_holiday_row_is_weekday(db_session):
    svc = HolidayService(db_session)
    assert svc.classify(dt.date(2026, 7, 27)) == DayClassification.WEEKDAY


def test_labor_day_classified_as_holiday(db_session):
    db_session.add(
        HolidayCalendar(
            calendar_date=dt.date(2026, 5, 1),
            holiday_type=HolidayType.LABOR_DAY,
            holiday_name="근로자의 날",
            is_weekend=False,
        )
    )
    db_session.commit()

    svc = HolidayService(db_session)
    assert svc.classify(dt.date(2026, 5, 1)) == DayClassification.HOLIDAY


def test_substitute_holiday_classified_as_holiday(db_session):
    db_session.add(
        HolidayCalendar(
            calendar_date=dt.date(2026, 3, 2),
            holiday_type=HolidayType.SUBSTITUTE,
            holiday_name="대체공휴일(삼일절)",
            is_weekend=False,
        )
    )
    db_session.commit()

    svc = HolidayService(db_session)
    assert svc.classify(dt.date(2026, 3, 2)) == DayClassification.HOLIDAY
    # 3/1 자체는 일요일이라 별도 row 없이도 휴일로 분류돼야 한다
    assert svc.classify(dt.date(2026, 3, 1)) == DayClassification.HOLIDAY


def test_classify_range(db_session):
    db_session.add(
        HolidayCalendar(
            calendar_date=dt.date(2026, 5, 1),
            holiday_type=HolidayType.LABOR_DAY,
            holiday_name="근로자의 날",
            is_weekend=False,
        )
    )
    db_session.commit()

    svc = HolidayService(db_session)
    result = svc.classify_range(dt.date(2026, 4, 30), dt.date(2026, 5, 3))
    assert result[dt.date(2026, 4, 30)] == DayClassification.WEEKDAY  # 목
    assert result[dt.date(2026, 5, 1)] == DayClassification.HOLIDAY  # 근로자의날(금)
    assert result[dt.date(2026, 5, 2)] == DayClassification.HOLIDAY  # 토
    assert result[dt.date(2026, 5, 3)] == DayClassification.HOLIDAY  # 일


def test_seed_data_loads_without_error(db_session):
    from app.seed.holidays_2025_2026 import HOLIDAY_SEED

    for calendar_date, holiday_type, name, note in HOLIDAY_SEED:
        db_session.add(
            HolidayCalendar(
                calendar_date=calendar_date,
                holiday_type=holiday_type,
                holiday_name=name,
                is_weekend=is_weekend(calendar_date),
                note=note,
            )
        )
    db_session.commit()

    svc = HolidayService(db_session)
    assert svc.classify(dt.date(2026, 5, 1)) == DayClassification.HOLIDAY  # 근로자의 날
    assert svc.classify(dt.date(2025, 12, 25)) == DayClassification.HOLIDAY  # 성탄절
    assert svc.classify(dt.date(2026, 7, 27)) == DayClassification.WEEKDAY
