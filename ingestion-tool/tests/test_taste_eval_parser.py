import datetime as dt

from models import MealType, TasteScore
from parsing.taste_eval_parser import TasteEvalParseError, find_header_row, parse_taste_eval_grid
import pytest

TITLE_ROW = ["식당 평가 리스트", "", "", "", "", "", "", "", ""]
HEADERS = ["N0", "취식일자", "Knox ID", "식사구분", "평가", "메뉴명", "의견", "평가의견", "IF 생성 날짜", "IF 수정 날짜"]


def _grid(*rows) -> list:
    return [TITLE_ROW, HEADERS, *rows]


def test_find_header_row_skips_title():
    assert find_header_row(_grid()) == 1


def test_basic_row_parsed():
    row = [1, "2026-06-25", "ccc.kim", "점심", "맛남", "해물잡탕밥", "", "", "2026-06-25 15:36:28", ""]
    rows = parse_taste_eval_grid(_grid(row))
    assert len(rows) == 1
    parsed = rows[0]
    assert parsed.eaten_date == dt.date(2026, 6, 25)
    assert parsed.knox_id == "ccc.kim"
    assert parsed.meal_type == MealType.LUNCH  # "점심" -> LUNCH
    assert parsed.taste_score == TasteScore.DELICIOUS
    assert parsed.menu_name == "해물잡탕밥"
    assert parsed.comment is None


def test_comment_from_either_column():
    row1 = [3, "2026-06-25", "ddd.lee", "점심", "보통", "해물잡탕밥", "청국장은 너무 식당 전체에 냄새가 심해요", "", "", ""]
    row2 = [4, "2026-06-25", "eee.park", "점심", "맛남", "파파돈가스", "", "재구매 의사 있음", "", ""]
    rows = parse_taste_eval_grid(_grid(row1, row2))
    assert rows[0].comment == "청국장은 너무 식당 전체에 냄새가 심해요"
    assert rows[1].comment == "재구매 의사 있음"


def test_blank_knox_id_skipped():
    row = [2, "2026-06-25", "", "점심", "맛남", "순두부청국장", "", "", "", ""]
    rows = parse_taste_eval_grid(_grid(row))
    assert rows == []


def test_missing_header_raises():
    with pytest.raises(TasteEvalParseError):
        parse_taste_eval_grid([TITLE_ROW, ["N0", "날짜", "코너"]])


def test_numeric_knox_id_from_excel_autoformat_not_left_with_decimal():
    # 엑셀이 순수 숫자로 된 Knox ID를 12345678.0(float)로 자동 변환해 넘기는
    # 실제 사례 — 그대로 두면 취식정보 쪽 "12345678"과 문자열이 달라져 매칭이
    # 100% 실패한다.
    row = [1, "2026-06-25", 12345678.0, "점심", "맛남", "해물잡탕밥", "", "", "", ""]
    rows = parse_taste_eval_grid(_grid(row))
    assert rows[0].knox_id == "12345678"
