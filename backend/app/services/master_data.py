"""ingestion-tool이 이름만 보내는 코너/메뉴/사번을 마스터 테이블과 매칭·생성한다."""

from sqlalchemy.orm import Session

from app.models.enums import Division
from app.models.master import CornerMaster, EmployeeMaster, MenuMaster

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


def get_or_create_employee(db: Session, employee_id: str) -> EmployeeMaster:
    """meal_log만으로는 본사/계열사/기타 구분을 알 수 없어 기본값 OTHER로 생성한다.

    실제 구분은 별도 HR 마스터 업로드(추후 구현)로 갱신하는 것을 전제로 한다.
    """
    employee = db.query(EmployeeMaster).filter_by(employee_id=employee_id).one_or_none()
    if employee is None:
        employee = EmployeeMaster(employee_id=employee_id, division=Division.OTHER)
        db.add(employee)
        db.flush()
    return employee
