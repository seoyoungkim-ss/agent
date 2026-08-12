import datetime as dt

from app.services.season import Season, classify_season


def test_february_is_winter():
    assert classify_season(dt.date(2026, 2, 28)) == Season.WINTER


def test_march_first_is_spring():
    assert classify_season(dt.date(2026, 3, 1)) == Season.SPRING


def test_may_last_day_is_spring():
    assert classify_season(dt.date(2026, 5, 31)) == Season.SPRING


def test_june_first_is_summer():
    assert classify_season(dt.date(2026, 6, 1)) == Season.SUMMER


def test_august_last_day_is_summer():
    assert classify_season(dt.date(2026, 8, 31)) == Season.SUMMER


def test_september_first_is_fall():
    assert classify_season(dt.date(2026, 9, 1)) == Season.FALL


def test_november_last_day_is_fall():
    assert classify_season(dt.date(2026, 11, 30)) == Season.FALL


def test_december_first_is_winter():
    assert classify_season(dt.date(2026, 12, 1)) == Season.WINTER


def test_january_is_winter_regardless_of_year():
    """연도는 무관하다 — 여러 해의 1월이 다 같은 겨울로 묶여야 한다."""
    assert classify_season(dt.date(2025, 1, 15)) == Season.WINTER
    assert classify_season(dt.date(2027, 1, 15)) == Season.WINTER
