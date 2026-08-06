import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, Date, Enum as SAEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import Division, FoodVectorSource, HolidayType
from app.services.food_vector import FOOD_VECTOR_DIM


class EmployeeMaster(Base):
    """PRD 4.1 employee_master. 개인 민감정보는 최소화한다."""

    __tablename__ = "employee_master"

    employee_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    division: Mapped[Division] = mapped_column(
        SAEnum(Division, values_callable=lambda e: [x.value for x in e], native_enum=False)
    )
    # 취식기록 "회사" 컬럼 원문 (예: 삼성전자/삼성SDI/지리산). division은 이 값을
    # app/services/company_classification.py로 분류한 결과이고, 계열사/기타라도
    # 실제 회사명은 이 필드로 그대로 노출한다.
    company_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    join_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class CornerMaster(Base):
    """PRD 4.1 corner_master. 그린미트는 is_diet_corner=True로 별도 분류(6.2)."""

    __tablename__ = "corner_master"

    corner_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corner_name: Mapped[str] = mapped_column(String(64), unique=True)
    is_diet_corner: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MenuMaster(Base):
    """PRD 4.1 menu_master. food_vector는 6.1의 개인 선호 벡터와 결합해 분석한다."""

    __tablename__ = "menu_master"

    menu_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    menu_name: Mapped[str] = mapped_column(String(128), unique=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    food_vector: Mapped[list[float] | None] = mapped_column(Vector(FOOD_VECTOR_DIM), nullable=True)
    # 규칙기반/LLM추정/관리자수동 — MANUAL은 이후 자동 재태깅 대상에서 제외된다.
    food_vector_source: Mapped[FoodVectorSource | None] = mapped_column(
        SAEnum(FoodVectorSource, values_callable=lambda e: [x.value for x in e], native_enum=False),
        nullable=True,
    )
    # 신메뉴 자동판정(weekly_menu_plan.is_new_menu, 최근 30일 창)을 관리자가
    # 직접 뒤집을 수 있게 하는 오버라이드 — None=자동판정 따름, True=강제로
    # "신메뉴 반응"에 노출(30일 창 무시, 해제 전까지 계속), False=자동판정이
    # True여도 강제로 숨김. new_menu_marked_on은 override를 True로 설정한
    # 시점 — "도입일"로 취급해 경과일 계산에 쓴다(2026-07).
    new_menu_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    new_menu_marked_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # 식재료 목록 — 한 끼 구성의 재료 중복 판정(menu_clash)에 쓴다. food_vector와
    # 똑같은 3단계(규칙 → LLM → 관리자수동)로 채우고, MANUAL은 재추출에서 제외한다.
    # 키워드 사전만으로는 사전에 없는 재료를 못 잡는다는 한계가 있어 LLM을 얹었다(2026-08).
    ingredients: Mapped[list[str] | None] = mapped_column(ARRAY(String(32)), nullable=True)
    ingredients_source: Mapped[FoodVectorSource | None] = mapped_column(
        SAEnum(FoodVectorSource, values_callable=lambda e: [x.value for x in e], native_enum=False),
        nullable=True,
    )


class HolidayCalendar(Base):
    """PRD 3.2 holiday_calendar. 근로자의 날/대체공휴일/회사자체휴무를 모두 포함한다."""

    __tablename__ = "holiday_calendar"

    calendar_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    holiday_type: Mapped[HolidayType] = mapped_column(
        SAEnum(HolidayType, values_callable=lambda e: [x.value for x in e], native_enum=False)
    )
    holiday_name: Mapped[str] = mapped_column(String(64))
    is_weekend: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
