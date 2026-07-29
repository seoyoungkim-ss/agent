"""식당취식정보(POS 결제 로그) 파싱 — 실제 컬럼 구조 기준 (25개 컬럼 중 분석에 쓰는 것만).

헤더 예시(순서 그대로): 일시, 부문명, 사업장명, 회사, 사원번호, 회사구분, 사원명,
급식업체, 식당, 코너, 단말기, 식구분, 포장구분, 메뉴구분, 메뉴명, 화면표시명(한글),
화면표시명(영문), 구분, 영수증번호, 결제수단, 수량, 귀속부서, CCTRCD, 직무, 정정여부

컬럼 순서가 아니라 **헤더 이름**으로 매칭하므로, 실제 파일에서 컬럼 순서가 달라도
안전하다.
"""

import datetime as dt
from collections.abc import Sequence
from typing import Any

from models import MealType, ParsedMealTransactionRow, normalize_meal_type

_REQUIRED_HEADERS = {
    "eaten_at": "일시",
    "department_name": "부문명",
    "worksite_name": "사업장명",
    "company_name": "회사",
    "employee_id": "사원번호",
    "company_type": "회사구분",
    "caterer": "급식업체",
    "restaurant": "식당",
    "corner_name": "코너",
    "meal_type": "식구분",
    "packaging": "포장구분",
    "menu_code_name": "메뉴명",
    "menu_display_name": "화면표시명(한글)",
    "receipt_no": "영수증번호",
    "status": "구분",
    "is_corrected": "정정여부",
}


class MealTransactionParseError(ValueError):
    pass


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _match_header(header_row: Sequence[Any]) -> dict[str, int]:
    normalized = [_clean(h).replace(" ", "") for h in header_row]
    column_index: dict[str, int] = {}
    missing: list[str] = []
    for field, header_name in _REQUIRED_HEADERS.items():
        target = header_name.replace(" ", "")
        if target in normalized:
            column_index[field] = normalized.index(target)
        else:
            missing.append(header_name)
    if missing:
        raise MealTransactionParseError(f"필수 컬럼을 찾지 못했습니다: {missing}")
    return column_index


_EXCEL_1900_EPOCH = dt.datetime(1899, 12, 30)  # 엑셀의 날짜 일련번호(serial date) 기준일


def _parse_datetime(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # CSV를 Excel로 열면 일부 셀이 날짜로 자동 인식되지 않고 엑셀 날짜
        # 일련번호(1899-12-30 기준 경과일수, 소수부는 하루 중 시각)로 그대로
        # 넘어오는 경우가 있다 — 예: 46112.79494... = 2026-03-31 19:04:43.
        total_seconds = round(value * 86400)
        return _EXCEL_1900_EPOCH + dt.timedelta(seconds=total_seconds)
    text = _clean(value)
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%d %I:%M:%S %p",  # 12시간제 + AM/PM, 예: "2026-03-31 7:04:43 PM"
    ):
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise MealTransactionParseError(f"일시를 해석할 수 없습니다: {value!r}")


def parse_meal_transaction_grid(grid: Sequence[Sequence[Any]]) -> list[ParsedMealTransactionRow]:
    if not grid:
        return []
    column_index = _match_header(grid[0])

    rows: list[ParsedMealTransactionRow] = []
    for raw_row in grid[1:]:
        if all(_clean(v) == "" for v in raw_row):
            continue

        def get(field: str) -> str:
            return _clean(raw_row[column_index[field]])

        meal_type_raw = get("meal_type")
        meal_type: MealType | None = normalize_meal_type(meal_type_raw)
        employee_id = get("employee_id")
        if not employee_id or meal_type is None:
            continue

        rows.append(
            ParsedMealTransactionRow(
                eaten_at=_parse_datetime(raw_row[column_index["eaten_at"]]),
                department_name=get("department_name"),
                worksite_name=get("worksite_name"),
                company_name=get("company_name"),
                employee_id=employee_id,
                company_type=get("company_type"),
                caterer=get("caterer"),
                restaurant=get("restaurant"),
                corner_name=get("corner_name"),
                meal_type=meal_type,
                packaging=get("packaging"),
                menu_code_name=get("menu_code_name"),
                menu_display_name=get("menu_display_name"),
                receipt_no=get("receipt_no"),
                status=get("status"),
                is_corrected=get("is_corrected").upper() == "Y",
            )
        )
    return rows
