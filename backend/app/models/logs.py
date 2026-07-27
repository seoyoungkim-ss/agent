import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import MealType, MenuRole, TasteScore
from app.services.food_vector import COMMENT_EMBEDDING_DIM


def _meal_type_col():
    return mapped_column(
        SAEnum(MealType, values_callable=lambda e: [x.value for x in e], native_enum=False)
    )


class WeeklyMenuPlan(Base):
    """PRD 4.1 weekly_menu_plan. 주간 식단표 파싱 결과 (ingestion-tool이 적재).

    source_row_raw에 원본 셀 원문을 남겨 파싱 검증에 사용한다 (PRD 2.2).
    """

    __tablename__ = "weekly_menu_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_date: Mapped[dt.date] = mapped_column(Date, index=True)
    meal_type: Mapped[MealType] = _meal_type_col()
    corner_id: Mapped[int] = mapped_column(ForeignKey("corner_master.corner_id"), index=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menu_master.menu_id"), index=True)
    menu_role: Mapped[MenuRole] = mapped_column(
        SAEnum(MenuRole, values_callable=lambda e: [x.value for x in e], native_enum=False)
    )
    is_new_menu: Mapped[bool] = mapped_column(Boolean, default=False)
    source_row_raw: Mapped[str | None] = mapped_column(Text, nullable=True)


class MealLog(Base):
    """PRD 4.1 meal_log. append-only 취식 로그. eaten_at은 초 단위까지 보존한다(6.2 피크타임 분석)."""

    __tablename__ = "meal_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    eaten_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employee_master.employee_id"), index=True)
    meal_type: Mapped[MealType] = _meal_type_col()
    corner_id: Mapped[int] = mapped_column(ForeignKey("corner_master.corner_id"), index=True)
    menu_id: Mapped[int | None] = mapped_column(
        ForeignKey("menu_master.menu_id"), nullable=True, index=True
    )
    taste_score: Mapped[TasteScore | None] = mapped_column(
        SAEnum(TasteScore, values_callable=lambda e: [x.value for x in e], native_enum=False),
        nullable=True,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(COMMENT_EMBEDDING_DIM), nullable=True
    )
    menu_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_menu_plan.id"), nullable=True
    )
    loaded_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
