import datetime as dt

from models import MealType, TasteScore
from parsing.meal_log_parser import MealLogParseError, parse_meal_log_grid
import pytest


def _sample_grid():
    return [
        ["취식일자", "사내ID", "식사구분", "코너", "맛평가", "주관식의견"],
        ["2026-07-20 11:52:03", "E12345", "중식", "한식", "맛남", "제육볶음 최고예요"],
        ["2026-07-20 12:01:30", "E67890", "중식", "그린미트", "보통", ""],
        [None, None, None, None, None, None],  # 빈 행은 skip
        ["2026-07-20 12:10:00", "E11111", "중식", "일품", "개선", None],
    ]


def test_parses_header_aliases_case_and_space_insensitive():
    grid = _sample_grid()
    grid[0][1] = "  사내id "
    rows = parse_meal_log_grid(grid)
    assert len(rows) == 3


def test_taste_score_mapped_correctly():
    rows = parse_meal_log_grid(_sample_grid())
    scores = {r.employee_id: r.taste_score for r in rows}
    assert scores["E12345"] == TasteScore.DELICIOUS
    assert scores["E67890"] == TasteScore.NORMAL
    assert scores["E11111"] == TasteScore.NEEDS_IMPROVEMENT


def test_comment_optional():
    rows = parse_meal_log_grid(_sample_grid())
    by_id = {r.employee_id: r.comment for r in rows}
    assert by_id["E12345"] == "제육볶음 최고예요"
    assert by_id["E67890"] is None
    assert by_id["E11111"] is None


def test_blank_row_skipped():
    rows = parse_meal_log_grid(_sample_grid())
    assert len(rows) == 3


def test_eaten_at_parsed_as_datetime():
    rows = parse_meal_log_grid(_sample_grid())
    row = next(r for r in rows if r.employee_id == "E12345")
    assert row.eaten_at == dt.datetime(2026, 7, 20, 11, 52, 3)


def test_meal_type_parsed():
    rows = parse_meal_log_grid(_sample_grid())
    assert all(r.meal_type == MealType.LUNCH for r in rows)


def test_missing_required_column_raises():
    grid = [["취식일자", "코너", "맛평가"], ["2026-07-20 11:00:00", "한식", "맛남"]]
    with pytest.raises(MealLogParseError):
        parse_meal_log_grid(grid)


def test_empty_grid_returns_empty_list():
    assert parse_meal_log_grid([]) == []
