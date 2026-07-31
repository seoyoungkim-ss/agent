from app.models.enums import Division
from app.services.master_data import (
    TAKE_OUT_CORNER_NAME,
    get_or_create_corner,
    get_or_create_employee,
    get_or_create_menu,
    normalize_employee_id,
)


def test_take_out_aliases_merge_into_single_corner(db_session):
    r, r_is_new = get_or_create_corner(db_session, "Take Out R")
    m, m_is_new = get_or_create_corner(db_session, "Take Out M")
    l, l_is_new = get_or_create_corner(db_session, "Take Out L")
    s, s_is_new = get_or_create_corner(db_session, "선택형 Take out")

    assert r_is_new is True
    assert m_is_new is False
    assert l_is_new is False
    assert s_is_new is False
    assert r.corner_id == m.corner_id == l.corner_id == s.corner_id
    assert r.corner_name == TAKE_OUT_CORNER_NAME


def test_unrelated_corner_name_unaffected(db_session):
    corner, is_new = get_or_create_corner(db_session, "한식")
    assert is_new is True
    assert corner.corner_name == "한식"


def test_normalize_employee_id_strips_excel_float_suffix():
    assert normalize_employee_id("12345678.0") == "12345678"
    assert normalize_employee_id("12345678") == "12345678"
    assert normalize_employee_id("knoxABC") == "knoxABC"


def test_get_or_create_employee_normalizes_dot_zero_suffix(db_session):
    employee = get_or_create_employee(db_session, "12345678.0", "삼성전자")
    assert employee.employee_id == "12345678"
    assert employee.division == Division.HEADQUARTERS

    # 정규화된 사번으로 다시 조회해도 같은 행을 찾아야 함(중복 생성 방지)
    same = get_or_create_employee(db_session, "12345678.0", "삼성전자")
    assert same.employee_id == employee.employee_id


def test_get_or_create_menu_strips_trailing_origin_annotation(db_session):
    menu, is_new = get_or_create_menu(db_session, "우삼겹구이(우육:호주산)")
    assert is_new is True
    assert menu.menu_name == "우삼겹구이"

    # 원산지 주석 없이 취식기록에서 들어오는 이름과 같은 행으로 매칭돼야 함
    same, same_is_new = get_or_create_menu(db_session, "우삼겹구이")
    assert same_is_new is False
    assert same.menu_id == menu.menu_id
