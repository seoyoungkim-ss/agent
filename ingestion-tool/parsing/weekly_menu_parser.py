"""PRD 2.2 / 9.2: 주간 식단표(병합 셀 포함) 파싱 로직.

입력은 xlwings로 읽어들인 "그리드"(list[list[Any]], 시트의 used_range.value)다.
Excel에서 병합된 셀은 병합 영역의 좌상단 셀에만 값이 들어있고 나머지는 빈 값으로
읽히므로, 조/중/석식 컬럼과 코너명 컬럼은 위에서 아래로 forward-fill해서 채운다.

메인/부찬 경계는 PRD에 명시된 대로 모호하다. 1차 규칙은 "요일 셀 안의 첫 줄(또는
첫 항목)을 메인, 나머지를 부찬"으로 가정한다 — 실제 데이터로 검증 후 조정이 필요하며,
이 규칙만 바꾸면 되도록 별도 함수(split_cell_into_items)로 분리해뒀다.
"""

import datetime as dt
import re
from collections.abc import Sequence
from typing import Any

from models import MealType, MenuRole, ParsedMenuRow

_MEAL_TYPE_VALUES = {m.value for m in MealType}
_WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]
_ITEM_SPLIT_PATTERN = re.compile(r"[\n\r]+|[,/·]")


class WeeklyMenuParseError(ValueError):
    pass


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def find_header_row(grid: Sequence[Sequence[Any]], first_day_col: int = 2) -> int:
    """월~일 요일 라벨이 들어있는 헤더 행의 인덱스를 찾는다."""
    for row_idx, row in enumerate(grid):
        labels = [_clean(row[c]) if c < len(row) else "" for c in range(first_day_col, first_day_col + 7)]
        matches = sum(1 for label, expected in zip(labels, _WEEKDAY_LABELS) if label == expected)
        if matches >= 5:  # 일부 셀이 비어 있어도 대부분 일치하면 헤더로 인정
            return row_idx
    raise WeeklyMenuParseError("월~일 요일 헤더 행을 찾지 못했습니다. first_day_col 설정을 확인하세요.")


def split_cell_into_items(raw_text: str) -> list[str]:
    """요일 셀 텍스트를 메뉴 항목 목록으로 분리한다 (첫 항목=메인, 나머지=부찬 가정)."""
    if not raw_text.strip():
        return []
    parts = [p.strip() for p in _ITEM_SPLIT_PATTERN.split(raw_text)]
    return [p for p in parts if p]


def _forward_fill_column(grid: Sequence[Sequence[Any]], col: int, start_row: int) -> list[str]:
    filled: list[str] = []
    last_value = ""
    for row in grid[start_row:]:
        cell = _clean(row[col]) if col < len(row) else ""
        if cell:
            last_value = cell
        filled.append(last_value)
    return filled


def parse_weekly_menu_grid(
    grid: Sequence[Sequence[Any]],
    week_start_date: dt.date,
    *,
    meal_type_col: int = 0,
    corner_col: int = 1,
    first_day_col: int = 2,
    header_row: int | None = None,
) -> list[ParsedMenuRow]:
    """주간 식단표 그리드를 weekly_menu_plan 행 목록으로 변환한다.

    week_start_date: 이 표가 나타내는 주의 월요일 날짜. 원본 표에는 요일만 있고
    절대 날짜가 없다고 가정하므로(PRD 2.2), 호출부(CLI)가 운영자에게 물어 전달한다.
    """
    if header_row is None:
        header_row = find_header_row(grid, first_day_col=first_day_col)

    data_rows = grid[header_row + 1 :]
    meal_types = _forward_fill_column(grid, meal_type_col, header_row + 1)
    corners = _forward_fill_column(grid, corner_col, header_row + 1)

    rows: list[ParsedMenuRow] = []
    for row_idx, row in enumerate(data_rows):
        meal_type_raw = meal_types[row_idx]
        corner_name = corners[row_idx]
        if meal_type_raw not in _MEAL_TYPE_VALUES or not corner_name:
            continue  # 조/중/석식 또는 코너명을 채울 수 없는 행(빈 줄 등)은 건너뜀
        meal_type = MealType(meal_type_raw)

        for day_offset in range(7):
            col = first_day_col + day_offset
            raw_text = _clean(row[col]) if col < len(row) else ""
            items = split_cell_into_items(raw_text)
            if not items:
                continue
            plan_date = week_start_date + dt.timedelta(days=day_offset)
            for item_idx, menu_name in enumerate(items):
                role = MenuRole.MAIN if item_idx == 0 else MenuRole.SIDE
                rows.append(
                    ParsedMenuRow(
                        plan_date=plan_date,
                        meal_type=meal_type,
                        corner_name=corner_name,
                        menu_name=menu_name,
                        menu_role=role,
                        source_row_raw=raw_text,
                    )
                )
    return rows
