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
_WEEKDAY_BY_PYTHON_INDEX = ["월", "화", "수", "목", "금", "토", "일"]  # dt.date.weekday(): 월=0
_SPECIAL_TAG_PATTERN = re.compile(r"^\[.+\]$")  # 예: "[한상차림]" — 메뉴명이 아니라 태그

# ---------------------------------------------------------------------------
# 원산지 주석 판정 (2026-08 재작성)
# ---------------------------------------------------------------------------
# 이전 구현은 구분자로 **콜론만** 인정해서 `(계육-국산)` 같은 하이픈 표기를 전부
# 부찬으로 흘려보냈다(실사용 신고). 게다가 항목 분리가 괄호 안 쉼표까지 잘라
# `우삼겹구이(우육:호주산, 돈육:국내산)`이 메인 이름을 `우삼겹구이(우육:호주산`으로
# 망가뜨렸다. 구분자를 넓히고, 분리를 괄호 밖에서만 하도록 함께 고친다.
#
# 구분자만 넓히면 `(오징어볶음-매운맛)` 같은 정상 표기까지 지워질 수 있어,
# **괄호 안 마지막 토큰이 원산지처럼 보여야 한다**는 조건을 함께 건다.
_ORIGIN_SEPARATOR_PATTERN = re.compile(r"[:\-–—/]|\s+")
_ORIGIN_EXPLICIT_TOKENS = {"국내산", "국산", "외국산", "수입산", "원양산"}
_ORIGIN_MARKER_PREFIXES = "*※ \t"


def _looks_like_origin_token(token: str) -> bool:
    """"국내산", "호주산", "브라질산"처럼 원산지 이름으로 보이는 마지막 토큰인가."""
    t = token.strip()
    if not t:
        return False
    if t in _ORIGIN_EXPLICIT_TOKENS:
        return True
    # "산"으로 끝나는 2~6자 — 국가/지역명 + 산. "매운맛"·"태양초" 등은 안 걸린다.
    return 2 <= len(t) <= 6 and t.endswith("산")


def _is_origin_entry(entry: str, *, allow_bare: bool = False) -> bool:
    """"우육:호주산" / "계육-국산" / "오징어 중국산" 한 건인지.

    allow_bare=True면 괄호 안에 원산지만 있는 `(중국산)` 형태도 인정한다 —
    괄호 밖에 메뉴명이 따로 있는 상황이라 오인 위험이 낮다.
    """
    parts = [p for p in _ORIGIN_SEPARATOR_PATTERN.split(entry.strip()) if p]
    if not parts:
        return False
    if len(parts) >= 2:
        return _looks_like_origin_token(parts[-1])
    return allow_bare and _looks_like_origin_token(parts[0])


def is_origin_annotation_text(text: str) -> bool:
    """이 셀/줄이 **통째로** 원산지 표기인가 — 그렇다면 메뉴가 아니라 버려야 한다.

    `(돈육:국내산, 고춧가루:중국산)`처럼 여러 재료가 나열된 경우도 잡는다.
    반대로 `우삼겹구이(우육:호주산)`처럼 **메뉴명이 앞에 붙어 있으면 False**를
    돌려준다 — 통째로 버리면 메뉴 자체가 사라지므로, 그건 뒤쪽 주석만 떼는
    `_strip_origin_annotation`이 담당한다.
    """
    t = text.strip().lstrip(_ORIGIN_MARKER_PREFIXES).strip()
    if not t:
        return False
    if t.startswith("(") and t.endswith(")"):
        inner, allow_bare = t[1:-1], True
    elif "(" not in t and ")" not in t:
        inner, allow_bare = t, False  # 괄호 없는 `*돈육:국내산` 형태
    else:
        return False  # 메뉴명 + 주석 혼합
    entries = [e for e in inner.split(",") if e.strip()]
    return bool(entries) and all(_is_origin_entry(e, allow_bare=allow_bare) for e in entries)


_TRAILING_PAREN_PATTERN = re.compile(r"\s*\(([^()]*)\)\s*$")


class WeeklyMenuParseError(ValueError):
    pass


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _weekday_label(value: Any) -> str:
    """헤더 셀에서 요일 라벨을 뽑아낸다.

    "7/6(월)"처럼 날짜서식이 입혀진 셀은 엑셀 화면에는 그렇게 보여도 실제
    값은 문자열이 아니라 datetime일 수 있다(xlwings가 셀 서식이 아니라
    값을 그대로 돌려줌) — 이 경우 str()로 바꾸면 요일 글자가 사라지므로,
    날짜 객체면 요일을 직접 계산해서 라벨을 만든다.
    """
    if isinstance(value, dt.datetime):
        value = value.date()
    if isinstance(value, dt.date):
        return _WEEKDAY_BY_PYTHON_INDEX[value.weekday()]
    return _clean(value)


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
    포함돼 있는지로 판단한다. 셀 값이 datetime이면 _weekday_label이 요일을
    직접 계산해준다.
    """
    threshold = max(1, num_days - 2)  # 기존 "7개 중 5개" 비율(≈71%)을 유지
    for row_idx, row in enumerate(grid):
        labels = []
        for day_offset in range(num_days):
            col = first_day_col + day_offset * day_col_span
            labels.append(_weekday_label(row[col]) if col < len(row) else "")
        matches = sum(1 for label, expected in zip(labels, _WEEKDAY_LABELS) if expected in label)
        if matches >= threshold:
            return row_idx
    raise WeeklyMenuParseError(
        "월~토 요일 헤더 행을 찾지 못했습니다. first_day_col/day_col_span 설정을 확인하세요."
    )


# ---------------------------------------------------------------------------
# 주차(week_start) 추론 — 헤더 셀의 날짜에서 뽑는다 (2026-08)
# ---------------------------------------------------------------------------
# 헤더 셀은 두 형태 중 하나다(_weekday_label 주석의 실사용 확인 참고):
#   1) datetime/date 객체 — 연도까지 정확
#   2) "7/6(월)" 문자열   — 월/일만 있고 연도가 없다
#
# ⚠️ 2번에서 연도를 "오늘과 가장 가까운 해"로 고르면 **안 된다.** 오늘이
# 2026-08-06일 때 "12/28"은 2026-12-28(144일 후)이 2025-12-28(222일 전)보다
# 가까워서 미래로 잘못 찍힌다. 과거 소급 적재는 연말을 반드시 넘으므로 이건
# 이론적 걱정이 아니다.
#
# 대신 **요일 라벨을 연도의 체크섬으로** 쓴다. 같은 월/일의 요일은 해마다
# 1~2일씩 밀리므로(윤년이면 2일), 후보 3년 안에서 요일은 절대 겹치지 않는다
# (오프셋 0, s₁, s₁+s₂ 이고 1≤s≤2 → 최대 4 < 7). 즉 요일이 맞는 해는 정확히
# 하나다. 예: "7/6(월)" → 2025=일, 2026=월, 2027=화 → 2026 확정.
_HEADER_DATE_PATTERN = re.compile(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})")
_YEAR_CANDIDATE_OFFSETS = (-1, 0, 1)


def _header_day_values(
    grid: Sequence[Sequence[Any]], header_row: int, first_day_col: int, day_col_span: int, num_days: int
) -> list[Any]:
    """헤더 행의 요일 열 **원본 값**. _weekday_label과 달리 날짜를 버리지 않는다."""
    row = grid[header_row]
    values = []
    for day_offset in range(num_days):
        col = first_day_col + day_offset * day_col_span
        values.append(row[col] if col < len(row) else None)
    return values


def _parse_header_date(value: Any, expected_weekday_label: str, today: dt.date) -> dt.date | None:
    """헤더 셀 하나에서 실제 날짜를 뽑는다. 못 뽑으면 None."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value

    match = _HEADER_DATE_PATTERN.search(_clean(value))
    if match is None:
        return None
    month, day = int(match.group(1)), int(match.group(2))

    matches = []
    for offset in _YEAR_CANDIDATE_OFFSETS:
        try:
            candidate = dt.date(today.year + offset, month, day)
        except ValueError:
            continue  # 2/29 같은 날짜가 그 해엔 없는 경우
        if _WEEKDAY_BY_PYTHON_INDEX[candidate.weekday()] == expected_weekday_label:
            matches.append(candidate)
    # 후보가 0개(요일이 안 맞음)거나 2개 이상이면 추측하지 않는다.
    return matches[0] if len(matches) == 1 else None


def infer_week_start(
    grid: Sequence[Sequence[Any]],
    *,
    first_day_col: int = 3,
    day_col_span: int = 2,
    num_days: int = 6,
    header_row: int | None = None,
    today: dt.date | None = None,
) -> dt.date:
    """이 표가 나타내는 주의 **월요일**을 헤더 날짜에서 알아낸다.

    운영자가 `--week-start`를 손으로 계산해 넣던 걸 대신한다. 판정에 조금이라도
    확신이 없으면 값을 만들어내지 않고 `WeeklyMenuParseError`를 올린다 —
    틀린 주로 적재하면 그 주의 편성이 통째로 어긋나고, 슬롯 교체(replace_existing)
    까지 켜져 있으면 **멀쩡한 다른 주를 지운다.**
    """
    today = today or dt.date.today()
    if header_row is None:
        header_row = find_header_row(
            grid, first_day_col=first_day_col, day_col_span=day_col_span, num_days=num_days
        )

    values = _header_day_values(grid, header_row, first_day_col, day_col_span, num_days)
    dates: list[dt.date | None] = [
        _parse_header_date(value, expected, today)
        for value, expected in zip(values, _WEEKDAY_LABELS)
    ]

    known = [(i, d) for i, d in enumerate(dates) if d is not None]
    if not known:
        raise WeeklyMenuParseError(
            "헤더에서 날짜를 읽지 못해 어느 주인지 알 수 없습니다. "
            "--week-start로 직접 지정하세요. "
            f"(헤더 {header_row}행 값: {[_clean(v) for v in values]})"
        )

    # 각 헤더 칸이 가리키는 월요일이 전부 같아야 한다. 하나라도 다르면 6일이
    # 연속이 아니라는 뜻 — 레이아웃이 다른 파일을 잘못된 날짜로 적재하느니
    # 실패시킨다.
    mondays = {d - dt.timedelta(days=i) for i, d in known}
    if len(mondays) > 1:
        raise WeeklyMenuParseError(
            "헤더의 요일별 날짜가 월~토 연속이 아닙니다 — 시트 레이아웃을 확인하세요. "
            f"(읽어낸 날짜: {[d.isoformat() for _, d in known]})"
        )

    monday = mondays.pop()
    if monday.weekday() != 0:
        raise WeeklyMenuParseError(
            f"추론된 주 시작일 {monday.isoformat()}이 월요일이 아닙니다 — "
            "요일 헤더와 날짜가 어긋나 있습니다."
        )
    return monday


def _strip_origin_annotation(name: str) -> str:
    """메뉴명 끝에 붙은 "(재료:원산지)" 주석을 제거해 메인메뉴명만 남긴다.

    괄호 안 마지막 토큰이 원산지처럼 보일 때만 뗀다 — `(오징어볶음-매운맛)`처럼
    메뉴 설명이 붙은 경우를 지우면 안 된다.
    """
    while True:
        match = _TRAILING_PAREN_PATTERN.search(name)
        if match is None:
            return name.strip()
        entries = [e for e in match.group(1).split(",") if e.strip()]
        if not entries or not all(_is_origin_entry(e, allow_bare=True) for e in entries):
            return name.strip()
        name = name[: match.start()].strip()


def _split_top_level(text: str) -> list[str]:
    """`,` `/` `·` 와 줄바꿈에서 자르되 **괄호 안에서는 자르지 않는다**.

    이걸 안 하면 `우삼겹구이(우육:호주산, 돈육:국내산)`이 괄호 한가운데서 잘려
    메인 이름이 `우삼겹구이(우육:호주산`으로 망가진다(2026-08 실사용 신고).
    """
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0 and (ch in ",/·" or ch in "\n\r"):
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [p for p in (x.strip() for x in out) if p]


def split_cell_into_items(raw_text: str) -> list[str]:
    """셀 텍스트를 메뉴 항목 목록으로 분리한다.

    "&"로 이어진 이름(예: "함박스테이크&소스")은 하나의 메뉴명으로 취급하고
    쪼개지 않는다 — 분리 패턴에 "&"가 없으므로 대부분 자연히 유지된다. 다만
    셀 안에서 "제육볶음&미니우동"이 줄바꿈으로 감싸져
    "제육볶음\n&미니우동"처럼 들어오면 줄바꿈 분리 때문에 "&미니우동"이라는
    조각난 항목이 생기므로, "&"로 시작하는 조각은 독립 항목으로 보지 않고
    바로 앞 항목에 다시 이어붙인다. 이름 끝에 붙은 원산지 주석(예:
    "우삼겹구이(우육:호주산)")은 제거한다.
    """
    if not raw_text.strip():
        return []
    # 통째로 원산지인 조각은 버리고, 메뉴명 뒤에 붙은 주석만 떼어낸다.
    parts = [
        _strip_origin_annotation(p)
        for p in _split_top_level(raw_text)
        if not is_origin_annotation_text(p)
    ]
    parts = [p for p in parts if p]
    items: list[str] = []
    for part in parts:
        if part.startswith("&") and items:
            items[-1] = items[-1] + part
        else:
            items.append(part)
    return items


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

    week_start_date: 이 표가 나타내는 주의 월요일 날짜. 표의 요일 칸에는 상대
    위치만 있으므로 절대 날짜는 이 인자로 받는다.

    ⚠️ 예전 주석은 "원본 표에는 요일만 있고 절대 날짜가 없다(PRD 2.2)"고 적혀
    있었지만 **사실이 아니다** — 헤더 셀에는 "7/6(월)"처럼 날짜가 함께 들어있고,
    날짜서식이면 xlwings가 datetime을 그대로 돌려준다(같은 파일의 find_header_row
    주석 참고). 그래서 호출부는 `infer_week_start(grid)`로 이 값을 자동으로 뽑을
    수 있고, CLI는 `--week-start`가 없을 때 그렇게 한다(2026-08).
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
                if is_origin_annotation_text(cell):
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
