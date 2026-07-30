"""PRD 2.2 / 9.2: 주간 식단표(병합 셀 포함) 파싱 로직.

실제 WeeklyMenu.xlsx 레이아웃(사용자 확인, 2026-07):
- A=조/중/석식, B-C=코너명(2열 병합), D-E=월요일, F-G=화요일, H-I=수요일,
  J-K=목요일, L-M=금요일, N-O=토요일 — 요일마다 2열씩 병합, 일요일은 식당
  미운영이라 없음(6일).
- 코너 하나가 여러 행에 걸친 "블록"이다: 블록 첫 행(코너명이 새로 나오는
  행)의 요일 칸에 메인메뉴가 있고, 그 아래 몇 행에 부찬이 한 행씩 이어지다가
  코너명이 다시 나오는 행에서 다음 코너 블록이 시작된다.
- 메인메뉴 자리에 "[한상차림]" 같은 대괄호 태그가 있으면 메뉴명이 아니라
  특별식 태그이고, 같은 열 바로 아래 행에 실제 메인메뉴가 있다.
- 메인메뉴 아래 "(우육:호주산)" 같은 재료/원산지 주석은 메뉴 데이터가
  아니므로 버린다.
- 메인메뉴가 "함박스테이크&소스"처럼 "&"로 이어진 경우는 하나의 메뉴명이다
  (분리 패턴에 "&"는 없으므로 자연히 유지됨).

입력은 xlwings로 읽어들인 "그리드"(list[list[Any]], 시트의 used_range.value)다.
병합된 셀은 좌상단 셀에만 값이 들어있고 나머지는 빈 값으로 읽히므로, 조/중/
석식·코너명·요일 헤더 모두 이 전제로 다룬다.
"""

import datetime as dt
import re
from collections.abc import Sequence
from typing import Any

from models import MealType, MenuRole, ParsedMenuRow

_MEAL_TYPE_VALUES = {m.value for m in MealType}
_WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토"]  # 일요일은 식당 미운영이라 없음
_ITEM_SPLIT_PATTERN = re.compile(r"[\n\r]+|[,/·]")
_SPECIAL_TAG_PATTERN = re.compile(r"^\[.+\]$")  # 예: "[한상차림]" — 메뉴명이 아니라 태그
_INGREDIENT_ANNOTATION_PATTERN = re.compile(r"^\(.+:.+\)$")  # 예: "(우육:호주산)" — 버림


class WeeklyMenuParseError(ValueError):
    pass


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def find_header_row(
    grid: Sequence[Sequence[Any]],
    *,
    first_day_col: int = 3,
    day_col_span: int = 2,
    num_days: int = 6,
) -> int:
    """월~토 요일 라벨이 들어있는 헤더 행의 인덱스를 찾는다.

    요일마다 두 열씩 병합돼 있어 라벨 값은 왼쪽 열에만 들어있다(오른쪽 열은
    빈 값) — 그리드 전체에서 값이 있는 행을 순서대로 스캔하므로 헤더가 몇
    번째 행에 있든(제목행이 앞에 있어도) 상관없다.

    실제 파일은 헤더 셀에 "7/6(월)"처럼 날짜가 요일과 함께 들어있어(사용자
    확인, 2026-07) 정확히 일치하지 않으므로, 요일 글자가 셀 텍스트 안에
    포함돼 있는지로 판단한다.
    """
    threshold = max(1, num_days - 2)  # 기존 "7개 중 5개" 비율(≈71%)을 유지
    for row_idx, row in enumerate(grid):
        labels = []
        for day_offset in range(num_days):
            col = first_day_col + day_offset * day_col_span
            labels.append(_clean(row[col]) if col < len(row) else "")
        matches = sum(1 for label, expected in zip(labels, _WEEKDAY_LABELS) if expected in label)
        if matches >= threshold:
            return row_idx
    raise WeeklyMenuParseError(
        "월~토 요일 헤더 행을 찾지 못했습니다. first_day_col/day_col_span 설정을 확인하세요."
    )


def split_cell_into_items(raw_text: str) -> list[str]:
    """셀 텍스트를 메뉴 항목 목록으로 분리한다.

    "&"로 이어진 이름(예: "함박스테이크&소스")은 하나의 메뉴명으로 취급하고
    쪼개지 않는다 — 분리 패턴에 "&"가 없으므로 자연히 유지된다.
    """
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


def _raw_column(grid: Sequence[Sequence[Any]], col: int, start_row: int) -> list[str]:
    return [_clean(row[col]) if col < len(row) else "" for row in grid[start_row:]]


def _block_start_indices(corners_raw: list[str]) -> list[int]:
    """코너명이 새로 채워진(병합 셀의 좌상단) 행 = 코너 블록 시작. 끝에 전체
    길이를 sentinel로 붙여 마지막 블록의 끝 경계로 쓴다."""
    starts = [i for i, value in enumerate(corners_raw) if value]
    starts.append(len(corners_raw))
    return starts


def parse_weekly_menu_grid(
    grid: Sequence[Sequence[Any]],
    week_start_date: dt.date,
    *,
    meal_type_col: int = 0,
    corner_col: int = 1,
    first_day_col: int = 3,
    day_col_span: int = 2,
    num_days: int = 6,
    header_row: int | None = None,
    included_meal_types: frozenset[MealType] = frozenset({MealType.LUNCH}),
) -> list[ParsedMenuRow]:
    """주간 식단표 그리드를 weekly_menu_plan 행 목록으로 변환한다.

    코너 하나가 여러 행에 걸친 "블록"이다(블록 첫 행=메인, 이어지는 행들=
    부찬). 지금은 included_meal_types에 해당하는 식사구분(기본: 중식)만
    파싱한다 — 조식/석식은 필요해지면 이 인자를 넓혀서 켠다.

    week_start_date: 이 표가 나타내는 주의 월요일 날짜. 원본 표에는 요일만
    있고 절대 날짜가 없으므로(PRD 2.2), 호출부(CLI)가 운영자에게 물어 전달한다.
    """
    if header_row is None:
        header_row = find_header_row(grid, first_day_col=first_day_col, day_col_span=day_col_span, num_days=num_days)

    body_start = header_row + 1
    meal_types = _forward_fill_column(grid, meal_type_col, body_start)
    corners_filled = _forward_fill_column(grid, corner_col, body_start)
    corners_raw = _raw_column(grid, corner_col, body_start)
    data_rows = grid[body_start:]

    block_starts = _block_start_indices(corners_raw)

    rows: list[ParsedMenuRow] = []
    for block_idx in range(len(block_starts) - 1):
        start = block_starts[block_idx]
        end = block_starts[block_idx + 1]

        meal_type_raw = meal_types[start]
        corner_name = corners_filled[start]
        if meal_type_raw not in _MEAL_TYPE_VALUES or not corner_name:
            continue  # 조/중/석식 또는 코너명을 채울 수 없는 블록은 건너뜀
        meal_type = MealType(meal_type_raw)
        if meal_type not in included_meal_types:
            continue

        for day_offset in range(num_days):
            col = first_day_col + day_offset * day_col_span
            plan_date = week_start_date + dt.timedelta(days=day_offset)

            main_name: str | None = None
            side_names: list[str] = []
            raw_texts: list[str] = []

            for row_idx in range(start, end):
                row = data_rows[row_idx]
                cell = _clean(row[col]) if col < len(row) else ""
                if not cell:
                    continue
                raw_texts.append(cell)  # 감사/디버깅용 — 버려지는 셀도 원문은 남긴다
                if _INGREDIENT_ANNOTATION_PATTERN.match(cell):
                    continue  # 재료/원산지 주석은 메뉴 데이터가 아니므로 버림
                if _SPECIAL_TAG_PATTERN.match(cell):
                    continue  # 특별식 태그 자체는 메뉴명이 아님 — 바로 아래 행이 실제 메인
                for item in split_cell_into_items(cell):
                    if main_name is None:
                        main_name = item
                    else:
                        side_names.append(item)

            if main_name is None:
                continue

            source_row_raw = " / ".join(raw_texts)
            rows.append(
                ParsedMenuRow(
                    plan_date=plan_date,
                    meal_type=meal_type,
                    corner_name=corner_name,
                    menu_name=main_name,
                    menu_role=MenuRole.MAIN,
                    source_row_raw=source_row_raw,
                )
            )
            for side_name in side_names:
                rows.append(
                    ParsedMenuRow(
                        plan_date=plan_date,
                        meal_type=meal_type,
                        corner_name=corner_name,
                        menu_name=side_name,
                        menu_role=MenuRole.SIDE,
                        source_row_raw=source_row_raw,
                    )
                )
    return rows
