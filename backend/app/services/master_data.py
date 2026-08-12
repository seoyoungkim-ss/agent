"""ingestion-tool이 이름만 보내는 코너/메뉴/사번을 마스터 테이블과 매칭·생성한다."""

import re

from sqlalchemy.orm import Session

from app.models.enums import FoodVectorSource
from app.models.master import CornerMaster, EmployeeMaster, MenuMaster
from app.services.company_classification import classify_division
from app.services.corner_aliases import (
    CORNER_ALIAS_MAP as _CORNER_ALIAS_MAP,
    MICAM_HALL_CORNER_NAME,
    SNAP_SNACK_ALIASES,
    SNAP_SNACK_CORNER_NAME,
    TAKE_OUT_ALIASES,
    TAKE_OUT_CORNER_NAME,
)
from app.services.food_vector_tagging import tag_food_vector_from_name
from app.services.menu_name import match_key, strip_origin_annotation

_GREEN_MEAT_NAMES = {"그린미트"}

# 테이크아웃 특성상(세부 메뉴를 정확히 못 남김) 개별 메뉴 단위 분석에 안 맞는
# 플레이스홀더성 메뉴명 — 4분면 집계, 메뉴 동반 선택 쌍(코어층 포함) 등 메뉴 단위
# 통계 전반에서 제외한다(2026-07 실사용 확인: "코너별 분석"의 메뉴 쌍에서도 계속
# 나온다는 후속 피드백으로, 4분면(aggregation.py)에만 있던 제외 목록을 여기로
# 옮겨 메뉴 동반선택(menu_affinity.py)과 공유).
PLACEHOLDER_MENU_NAMES = {"선택형 Take out", "(포장)메디쏠라"}

_TRAILING_DOT_ZERO = re.compile(r"^(\d+)\.0$")

# 메뉴명 끝에 "(재료:원산지)" 같은 주석이 붙어 들어오는 경로를 방어한다(파싱
# 단계에서 이미 제거하지만, 취식기록/맛평가 쪽은 원산지 정보가 없으므로 여기서도
# 한 번 더 정규화해 두 경로의 메뉴명이 항상 같은 MenuMaster row로 모이게 한다).
#
# ⚠️ 아래 판정은 `ingestion-tool/parsing/weekly_menu_parser.py`와 **같은 규칙**이다.
# 두 패키지가 분리돼 코드를 공유할 수 없어 복제하고 있으므로, 한쪽만 고치면
# 조용히 어긋난다 — 실제로 2026-08까지 콜론만 인정하는 낡은 정규식이 양쪽에
# 복제돼 있었고(`(계육-국산)`을 둘 다 못 걸렀다), 그래서 양쪽에 같은 케이스
# 테스트를 두어 어긋나면 깨지게 했다.
def normalize_employee_id(employee_id: str) -> str:
    """엑셀이 숫자만 있는 사번을 "12345678.0"으로 자동변환하는 경우를 되돌린다.

    ingestion-tool 쪽에서 이미 막아뒀지만(2026-07 수정), 다른 경로로 들어오는
    값까지 방어하려고 이 신뢰 경계(백엔드 저장 직전)에도 한 번 더 둔다.
    """
    match = _TRAILING_DOT_ZERO.match(employee_id)
    return match.group(1) if match else employee_id


def _normalize_corner_name(corner_name: str) -> str:
    return _CORNER_ALIAS_MAP.get(corner_name, corner_name)


def _normalize_menu_name(menu_name: str) -> str:
    """메뉴명 끝의 원산지 주석을 뗀다 — 판정은 menu_name.py가 단일 출처다."""
    return strip_origin_annotation(menu_name)


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
    menu_name = _normalize_menu_name(menu_name)
    # ⚠️ 이름이 아니라 **매칭 키**로 찾는다(2026-08). 이름으로 찾으면 `연어 파피요트`와
    # `연어파피요트`가 별개 행이 돼 식단표와 취식기록이 서로 안 붙는다.
    # 같은 키를 가진 행이 여럿이면(예전에 갈라진 것들) 가장 먼저 만들어진 걸 쓴다 —
    # 정리는 `app/maintenance/merge_duplicate_menus.py`가 한다.
    key = match_key(menu_name)
    menu = (
        db.query(MenuMaster)
        .filter(MenuMaster.match_key == key)
        .order_by(MenuMaster.menu_id)
        .first()
    )
    if menu is None:
        vector, matched_any = tag_food_vector_from_name(menu_name)
        menu = MenuMaster(
            menu_name=menu_name,
            match_key=key,
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
    employee_id = normalize_employee_id(employee_id)
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


def find_menu_by_name(db: Session, menu_name: str) -> MenuMaster | None:
    """표기가 달라도 찾아주는 메뉴 조회 (2026-08).

    `match_key`로 먼저 찾고, 없으면 이름 정확 일치로 폴백한다. 담당자가 검색창에
    `연어 파피요트`라고 띄어 써도 `연어파피요트`가 나와야 한다 — `get_or_create_menu`만
    키를 쓰게 바꿔놔서 조회 화면들은 여전히 못 찾고 있었다.

    폴백을 남기는 이유: `match_key`가 아직 안 채워진 행이 남아 있을 수 있고,
    그때 조용히 "없음"이 되는 것보다 이름으로라도 찾는 게 낫다.
    """
    key = match_key(menu_name)
    menu = (
        db.query(MenuMaster)
        .filter(MenuMaster.match_key == key)
        .order_by(MenuMaster.menu_id)
        .first()
    )
    if menu is not None:
        return menu
    return db.query(MenuMaster).filter(MenuMaster.menu_name == menu_name).first()
