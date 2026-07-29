import datetime as dt

from models import MealType
from parsing.meal_transaction_parser import MealTransactionParseError, parse_meal_transaction_grid
import pytest

HEADERS = [
    "일시", "부문명", "사업장명", "회사", "사원번호", "회사구분", "사원명", "급식업체",
    "식당", "코너", "단말기", "식구분", "포장구분", "메뉴구분", "메뉴명",
    "화면표시명(한글)", "화면표시명(영문)", "구분", "영수증번호", "결제수단", "수량",
    "귀속부서", "CCTRCD", "직무", "정정여부",
]


def _row(**overrides) -> list:
    base = {
        "일시": "2026-06-25 12:05:00",
        "부문명": "Aa 부문",
        "사업장명": "기술캠퍼스",
        "회사": "지리산",
        "사원번호": "14131244",
        "회사구분": "관계사",
        "사원명": "박휘*",
        "급식업체": "웰스토리",
        "식당": "SAIT",
        "코너": "고슬고슬비빔",
        "단말기": "POS003",
        "식구분": "중식",
        "포장구분": "DINE_IN",
        "메뉴구분": "일반식",
        "메뉴명": "고슬고슬비빔1",
        "화면표시명(한글)": "해물잡탕밥",
        "화면표시명(영문)": "Seafood Rice",
        "구분": "정상",
        "영수증번호": "100001",
        "결제수단": "사원결제",
        "수량": "1",
        "귀속부서": "연구1그룹(컴퓨팅센터)",
        "CCTRCD": "",
        "직무": "",
        "정정여부": "N",
    }
    base.update(overrides)
    return [base[h] for h in HEADERS]


def _grid(*rows) -> list:
    return [HEADERS, *rows]


def test_basic_row_parsed():
    rows = parse_meal_transaction_grid(_grid(_row()))
    assert len(rows) == 1
    row = rows[0]
    assert row.eaten_at == dt.datetime(2026, 6, 25, 12, 5, 0)
    assert row.employee_id == "14131244"
    assert row.company_type == "관계사"
    assert row.meal_type == MealType.LUNCH
    assert row.corner_name == "고슬고슬비빔"
    assert row.menu_display_name == "해물잡탕밥"
    assert row.is_corrected is False


def test_blank_employee_id_skipped():
    # 협력사 직원은 사원번호가 비어 있는 실제 사례가 있다 — 매칭 불가하므로 skip
    rows = parse_meal_transaction_grid(_grid(_row(사원번호="", 회사구분="협력사")))
    assert rows == []


def test_unrecognized_meal_type_skipped():
    rows = parse_meal_transaction_grid(_grid(_row(식구분="야식")))
    assert rows == []


def test_correction_flag_parsed():
    rows = parse_meal_transaction_grid(_grid(_row(정정여부="Y")))
    assert rows[0].is_corrected is True


def test_missing_required_column_raises():
    bad_headers = [h for h in HEADERS if h != "사원번호"]
    with pytest.raises(MealTransactionParseError):
        parse_meal_transaction_grid([bad_headers])


def test_column_order_independent():
    # 헤더 이름으로 매칭하므로 컬럼 순서를 뒤섞어도 정상 파싱돼야 함
    shuffled = list(reversed(HEADERS))
    row = _row()
    value_by_header = dict(zip(HEADERS, row))
    shuffled_row = [value_by_header[h] for h in shuffled]
    rows = parse_meal_transaction_grid([shuffled, shuffled_row])
    assert rows[0].employee_id == "14131244"


def test_blank_row_skipped():
    rows = parse_meal_transaction_grid(_grid(_row(), ["" for _ in HEADERS]))
    assert len(rows) == 1


def test_12_hour_am_pm_datetime_parsed():
    # 실측 데이터의 일시 형식: "2026-03-31  7:04:43 PM" (12시간제, 시 0-padding 없음,
    # 날짜-시간 사이 공백 2개 — strptime은 포맷 문자열의 공백을 \s+로 컴파일하므로
    # 공백 개수 차이는 문제되지 않는다).
    rows = parse_meal_transaction_grid(_grid(_row(일시="2026-03-31  7:04:43 PM")))
    assert rows[0].eaten_at == dt.datetime(2026, 3, 31, 19, 4, 43)


def test_12_hour_am_datetime_parsed():
    rows = parse_meal_transaction_grid(_grid(_row(일시="2026-03-31 7:04:43 AM")))
    assert rows[0].eaten_at == dt.datetime(2026, 3, 31, 7, 4, 43)


def test_excel_serial_date_number_parsed():
    # CSV를 Excel로 열면 날짜로 자동 인식되지 않은 셀이 일련번호(float)로 그대로
    # 넘어오는 실제 사례 — 46112.79494212963 == 2026-03-31 19:04:43 (위 AM/PM
    # 테스트와 동일 시각, 표현 방식만 다름).
    rows = parse_meal_transaction_grid(_grid(_row(일시=46112.79494212963)))
    assert rows[0].eaten_at == dt.datetime(2026, 3, 31, 19, 4, 43)


def test_numeric_employee_id_from_excel_autoformat_not_left_with_decimal():
    # 엑셀이 순수 숫자로 된 사원번호를 14131244.0(float)로 자동 변환해 넘기는
    # 실제 사례 — 그대로 두면 맛평가 쪽 매핑 결과 "14131244"와 문자열이 달라져
    # 매칭이 100% 실패한다.
    rows = parse_meal_transaction_grid(_grid(_row(사원번호=14131244.0)))
    assert rows[0].employee_id == "14131244"
