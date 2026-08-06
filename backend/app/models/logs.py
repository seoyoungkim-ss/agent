import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import MealType, MenuRole, MenuRoleSource, TasteScore
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
    # 한 슬롯(날짜·코너·식사구분)에 같은 메뉴가 같은 역할로 두 번 있을 이유가 없다.
    # 2026-08에 재적재가 관리자 수동 수정 행과 새 파싱 행을 함께 남겨 부찬이 두
    # 벌씩 생겼는데 **에러 없이 조용히** 망가졌다 — 같은 사고가 다시 나면 이번엔
    # 즉시 터지게 한다. 정상 입력이 여기 걸리지 않도록 api/ingest.py가 payload 내
    # 중복을 먼저 제거한다.
    __table_args__ = (
        UniqueConstraint(
            "plan_date",
            "corner_id",
            "meal_type",
            "menu_id",
            "menu_role",
            name="uq_weekly_menu_plan_slot_menu_role",
        ),
    )

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
    # 주찬/부찬 판별이 어떻게 됐는지 — ingestion-tool의 위치 규칙(첫 항목=메인)이
    # 기본값이고, LLM 일괄 재분류(weekly_menu_role_llm.py)나 관리자 수동 수정(2.0
    # 주간 식단표 관리 화면)으로 바뀔 수 있다. MANUAL이면 이후 자동 배치가 안 건드림.
    role_source: Mapped[MenuRoleSource] = mapped_column(
        SAEnum(MenuRoleSource, values_callable=lambda e: [x.value for x in e], native_enum=False),
        default=MenuRoleSource.RULE,
    )


class WeeklyMenuFeedback(Base):
    """관리자가 "주간 식단표 관리" 화면에서 남기는 개선의견.

    식당에서 식단표를 2주 전에 전달하고, 관리자는 plan_date - 7일까지 의견을
    낼 수 있다는 운영 규칙이 있다(app/services/weekly_menu_review.py::
    feedback_deadline) — 이 테이블 자체는 마감과 무관하게 항상 저장하고,
    마감 여부 판단은 조회 시점에 계산한다.
    """

    __tablename__ = "weekly_menu_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_date: Mapped[dt.date] = mapped_column(Date, index=True)
    corner_id: Mapped[int] = mapped_column(ForeignKey("corner_master.corner_id"), index=True)
    comment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


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
    # PRD 5.2/5.3: 월간 VOE 고정 분류(맛/간/위생/서비스)의 LLM 배치 결과 — 매달
    # app/services/voe_category_llm.py가 채운다(누적 저장, 매번 재호출하지 않음).
    # NULL이면 아직 배치가 안 돈 것 — app/api/dashboard.py::voe_by_category가
    # 이 경우만 규칙 기반(voe_category.py)으로 그때그때 대체한다.
    voe_categories: Mapped[list[str] | None] = mapped_column(ARRAY(String(16)), nullable=True)
    voe_keywords: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)), nullable=True)
    menu_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_menu_plan.id"), nullable=True
    )
    loaded_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
