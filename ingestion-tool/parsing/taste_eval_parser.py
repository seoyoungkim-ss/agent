"""식당 평가 리스트("맛평가") 파싱.

실제 헤더: N0, 취식일자, Knox ID, 식사구분, 평가, 메뉴명, 의견, 평가의견,
IF 생성 날짜, IF 수정 날짜. 시트 맨 위에 "식당 평가 리스트" 제목 행이 있어서
헤더 행을 자동으로 찾는다. 취식일자에는 시간 정보가 없다(날짜만).
"""

import datetime as dt
from collections.abc import Sequence
from typing import Any

from models import MealType, ParsedTasteEvalRow, TasteScore, normalize_meal_type

_HEADER_NAMES = {
    "eaten_date": "취식일자",
    "knox_id": "KnoxID",
    "meal_type": "식사구분",
    "taste_score": "평가",
    "menu_name": "메뉴명",
    "comment_1": "의견",
    "comment_2": "평가의견",
}


class TasteEvalParseError(ValueError):
    pass


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def find_header_row(grid: Sequence[Sequence[Any]]) -> int:
    for row_idx, row in enumerate(grid):
        normalized = {_clean(c).replace(" ", "") for c in row}
        if "취식일자" in normalized and "KnoxID" in normalized:
            return row_idx
    raise TasteEvalParseError("헤더 행(취식일자, Knox ID 포함)을 찾지 못했습니다.")


def _match_header(header_row: Sequence[Any]) -> dict[str, int]:
    normalized = [_clean(h).replace(" ", "") for h in header_row]
    column_index: dict[str, int] = {}
    for field, name in _HEADER_NAMES.items():
        target = name.replace(" ", "")
        if target in normalized:
            column_index[field] = normalized.index(target)
    missing = [_HEADER_NAMES[f] for f in ("eaten_date", "knox_id", "meal_type", "taste_score", "menu_name") if f not in column_index]
    if missing:
        raise TasteEvalParseError(f"필수 컬럼을 찾지 못했습니다: {missing}")
    return column_index


def _parse_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = _clean(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise TasteEvalParseError(f"취식일자를 해석할 수 없습니다: {value!r}")


def parse_taste_eval_grid(grid: Sequence[Sequence[Any]]) -> list[ParsedTasteEvalRow]:
    if not grid:
        return []
    header_row = find_header_row(grid)
    column_index = _match_header(grid[header_row])

    rows: list[ParsedTasteEvalRow] = []
    for raw_row in grid[header_row + 1 :]:
        if all(_clean(v) == "" for v in raw_row):
            continue

        def get(field: str) -> str:
            idx = column_index.get(field)
            return _clean(raw_row[idx]) if idx is not None else ""

        taste_raw = get("taste_score")
        meal_type: MealType | None = normalize_meal_type(get("meal_type"))
        knox_id = get("knox_id")
        if not knox_id or meal_type is None or taste_raw not in {t.value for t in TasteScore}:
            continue

        comment_parts = [c for c in (get("comment_1"), get("comment_2")) if c]
        comment = " / ".join(comment_parts) if comment_parts else None

        rows.append(
            ParsedTasteEvalRow(
                eaten_date=_parse_date(raw_row[column_index["eaten_date"]]),
                knox_id=knox_id,
                meal_type=meal_type,
                taste_score=TasteScore(taste_raw),
                menu_name=get("menu_name"),
                comment=comment,
            )
        )
    return rows
