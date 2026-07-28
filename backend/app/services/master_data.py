"""ingestion-tool이 이름만 보내는 코너/메뉴/사번을 마스터 테이블과 매칭·생성한다."""

from sqlalchemy.orm import Session

from app.models.master import CornerMaster, EmployeeMaster, MenuMaster
from app.services.company_classification import classify_division

_GREEN_MEAT_NAMES = {"그린미트"}


def get_or_create_corner(db: Session, corner_name: str) -> tuple[CornerMaster, bool]:
    """returns (corner, is_new)."""
    corner = db.query(CornerMaster).filter_by(corner_name=corner_name).one_or_none()
    if corner is None:
        corner = CornerMaster(corner_name=corner_name, is_diet_corner=corner_name in _GREEN_MEAT_NAMES)
        db.add(corner)
        db.flush()
        return corner, True
    return corner, False


def get_or_create_menu(db: Session, menu_name: str) -> tuple[MenuMaster, bool]:
    """returns (menu, is_new) — is_new는 이번에 menu_master에 처음 생성됐는지."""
    menu = db.query(MenuMaster).filter_by(menu_name=menu_name).one_or_none()
    if menu is None:
        menu = MenuMaster(menu_name=menu_name)
        db.add(menu)
        db.flush()
        return menu, True
    return menu, False


def get_or_create_employee(
    db: Session, employee_id: str, company_name: str | None = None
) -> EmployeeMaster:
    """식당취식정보의 "회사" 원문(company_name)으로 본사/계열사/기타를 분류한다
    (app/services/company_classification.py). company_name이 없는 소스(과거 방식
    호환)는 기타로 남는다.

    매번 최신 company_name/division으로 갱신한다 — 사람이 회사를 옮기거나, 분류
    매핑(COMPANY_DIVISION_MAP)이 나중에 바뀌어도 다음 배치 인입 때 자동 반영되게
    하려는 의도.
    """
    employee = db.query(EmployeeMaster).filter_by(employee_id=employee_id).one_or_none()
    division = classify_division(company_name)
    if employee is None:
        employee = EmployeeMaster(employee_id=employee_id, division=division, company_name=company_name)
        db.add(employee)
        db.flush()
    elif company_name:
        employee.company_name = company_name
        employee.division = division
    return employee
