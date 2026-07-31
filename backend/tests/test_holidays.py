import datetime as dt

from app.models.enums import HolidayType
from app.models.master import HolidayCalendar
from app.services.holidays import (
    DayClassification,
    HolidayService,
    family_day_dates_in_range,
    family_day_of_month,
    is_family_day,
    is_weekend,
)


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


def test_family_day_of_month_falls_on_friday_of_week_containing_21st():
    # 2026-07-21은 화요일 → 그 주(20~26일)의 금요일은 7/24
    assert family_day_of_month(2026, 7) == dt.date(2026, 7, 24)
    # 2026-06-21은 일요일 → 그 주(15~21일)의 금요일은 6/19
    assert family_day_of_month(2026, 6) == dt.date(2026, 6, 19)
    # 2026-02-21은 토요일 → 그 주(16~22일)의 금요일은 2/20
    assert family_day_of_month(2026, 2) == dt.date(2026, 2, 20)


def test_is_family_day_true_only_for_the_computed_friday():
    assert is_family_day(dt.date(2026, 7, 24))
    assert not is_family_day(dt.date(2026, 7, 17))  # 그 전주 금요일
    assert not is_family_day(dt.date(2026, 7, 21))  # 21일 자체(화요일)


def test_family_day_dates_in_range_collects_each_overlapping_month():
    dates = family_day_dates_in_range(dt.date(2026, 6, 1), dt.date(2026, 7, 31))
    assert dates == {dt.date(2026, 6, 19), dt.date(2026, 7, 24)}


def test_family_day_dates_in_range_excludes_dates_outside_bounds():
    dates = family_day_dates_in_range(dt.date(2026, 7, 1), dt.date(2026, 7, 20))
    assert dates == set()


def test_classify_family_day_friday_as_family_day(db_session):
    svc = HolidayService(db_session)
    assert svc.classify(dt.date(2026, 7, 24)) == DayClassification.FAMILY_DAY


def test_classify_prefers_holiday_over_family_day_when_they_coincide(db_session):
    db_session.add(
        HolidayCalendar(
            calendar_date=dt.date(2026, 7, 24),
            holiday_type=HolidayType.SUBSTITUTE,
            holiday_name="임시공휴일",
            is_weekend=False,
        )
    )
    db_session.commit()

    svc = HolidayService(db_session)
    assert svc.classify(dt.date(2026, 7, 24)) == DayClassification.HOLIDAY


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
