"""ingestion-tool이 이름만 보내는 코너/메뉴/사번을 마스터 테이블과 매칭·생성한다."""

from sqlalchemy.orm import Session

from app.models.enums import FoodVectorSource
from app.models.master import CornerMaster, EmployeeMaster, MenuMaster
from app.services.company_classification import classify_division
from app.services.food_vector_tagging import tag_food_vector_from_name

_GREEN_MEAT_NAMES = {"그린미트"}

TAKE_OUT_CORNER_NAME = "Take Out"
# 취식기록 "코너" 컬럼 원문 — 같은 Take Out을 R/M/L 세 단말기로 나눠 찍는다(2026-07
# 실사용 확인). 세 이름 모두 하나의 코너로 합친다.
TAKE_OUT_ALIASES = {"Take Out R", "Take Out M", "Take Out L"}


def _normalize_corner_name(corner_name: str) -> str:
    return TAKE_OUT_CORNER_NAME if corner_name in TAKE_OUT_ALIASES else corner_name


def get_or_create_corner(db: Session, corner_name: str) -> tuple[CornerMaster, bool]:
    """returns (corner, is_new)."""
    corner_name = _normalize_corner_name(corner_name)
    corner = db.query(CornerMaster).filter_by(corner_name=corner_name).one_or_none()
    if corner is None:
        corner = CornerMaster(corner_name=corner_name, is_diet_corner=corner_name in _GREEN_MEAT_NAMES)
        db.add(corner)
        db.flush()
        return corner, True
    return corner, False


def get_or_create_menu(db: Session, menu_name: str) -> tuple[MenuMaster, bool]:
    """returns (menu, is_new) — is_new는 이번에 menu_master에 처음 생성됐는지.

    신메뉴는 이름 기반 규칙(food_vector_tagging.py)으로 즉시 1차 태깅을 시도한다.
    규칙이 아무것도 못 잡으면 food_vector를 NULL로 남겨 이후 LLM 배치/관리자 수동
    조정을 기다린다.
    """
    menu = db.query(MenuMaster).filter_by(menu_name=menu_name).one_or_none()
    if menu is None:
        vector, matched_any = tag_food_vector_from_name(menu_name)
        menu = MenuMaster(
            menu_name=menu_name,
            food_vector=vector if matched_any else None,
            food_vector_source=FoodVectorSource.RULE if matched_any else None,
        )
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
