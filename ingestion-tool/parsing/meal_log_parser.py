"""PRD 2.1 / 9.2: 취식 로그(mealdata.csv, DRM으로 Excel을 통해 열어야 함) 파싱 로직.

입력은 xlwings로 읽은 그리드(list[list[Any]])이며, 첫 행이 헤더(취식일자, 사내ID,
식사구분, 코너, 맛평가, 주관식의견)라고 가정한다. 헤더 이름의 공백/표기 편차에
어느 정도 관대하게 매칭한다.
"""

import datetime as dt
from collections.abc import Sequence
from typing import Any

from models import MealType, ParsedMealLogRow, TasteScore

_HEADER_ALIASES: dict[str, list[str]] = {
    "eaten_at": ["취식일자", "취식일시", "일시"],
    "employee_id": ["사내id", "사내ID", "사번", "employee_id"],
    "meal_type": ["식사구분"],
    "corner": ["코너", "코너명"],
    "taste_score": ["맛평가"],
    "comment": ["주관식의견", "의견", "코멘트"],
}


class MealLogParseError(ValueError):
    pass


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _match_header(header_row: Sequence[Any]) -> dict[str, int]:
    normalized = [_clean(h).lower().replace(" ", "") for h in header_row]
    column_index: dict[str, int] = {}
    for field, aliases in _HEADER_ALIASES.items():
        for alias in aliases:
            alias_norm = alias.lower().replace(" ", "")
            if alias_norm in normalized:
                column_index[field] = normalized.index(alias_norm)
                break
    missing = set(_HEADER_ALIASES) - {"comment"} - set(column_index)
    if missing:
        raise MealLogParseError(f"필수 컬럼을 찾지 못했습니다: {sorted(missing)}")
    return column_index


def _parse_datetime(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())
    text = _clean(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise MealLogParseError(f"취식일자를 해석할 수 없습니다: {value!r}")


def parse_meal_log_grid(grid: Sequence[Sequence[Any]]) -> list[ParsedMealLogRow]:
    if not grid:
        return []
    column_index = _match_header(grid[0])

    rows: list[ParsedMealLogRow] = []
    for raw_row in grid[1:]:
        if all(_clean(v) == "" for v in raw_row):
            continue  # 완전 빈 행 skip

        employee_id = _clean(raw_row[column_index["employee_id"]])
        meal_type_raw = _clean(raw_row[column_index["meal_type"]])
        corner_name = _clean(raw_row[column_index["corner"]])
        taste_raw = _clean(raw_row[column_index["taste_score"]])
        comment_idx = column_index.get("comment")
        comment = _clean(raw_row[comment_idx]) if comment_idx is not None else ""

        if not employee_id or meal_type_raw not in {m.value for m in MealType}:
            continue

        rows.append(
            ParsedMealLogRow(
                eaten_at=_parse_datetime(raw_row[column_index["eaten_at"]]),
                employee_id=employee_id,
                meal_type=MealType(meal_type_raw),
                corner_name=corner_name,
                taste_score=TasteScore(taste_raw) if taste_raw in {t.value for t in TasteScore} else None,
                comment=comment or None,
            )
        )
    return rows
