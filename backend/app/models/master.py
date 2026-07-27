import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, Enum as SAEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import Division, HolidayType
from app.services.food_vector import FOOD_VECTOR_DIM


class EmployeeMaster(Base):
    """PRD 4.1 employee_master. 개인 민감정보는 최소화한다."""

    __tablename__ = "employee_master"

    employee_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    division: Mapped[Division] = mapped_column(
        SAEnum(Division, values_callable=lambda e: [x.value for x in e], native_enum=False)
    )
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
