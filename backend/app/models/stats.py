import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import Division, MealType, MenuQuadrant
from app.services.food_vector import FOOD_VECTOR_DIM


def _meal_type_col():
    return mapped_column(
        SAEnum(MealType, values_callable=lambda e: [x.value for x in e], native_enum=False)
    )


class DailyCornerStats(Base):
    """PRD 4.2 daily_corner_stats. 일자·코너·식사구분별 이용자수/만족도/서브속도(6.2)."""

    __tablename__ = "daily_corner_stats"
    __table_args__ = (UniqueConstraint("stat_date", "corner_id", "meal_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stat_date: Mapped[dt.date] = mapped_column(Date, index=True)
    corner_id: Mapped[int] = mapped_column(ForeignKey("corner_master.corner_id"), index=True)
    meal_type: Mapped[MealType] = _meal_type_col()
    headcount: Mapped[int] = mapped_column(Integer, default=0)
    avg_taste_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # PRD 6.2: 피크타임(11:40~12:00) 취식 로그를 초단위로 집계한 분당 평균 서빙 처리량
    peak_throughput_per_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_holiday: Mapped[bool] = mapped_column(default=False)


class DailyDivisionStats(Base):
    """PRD 4.2 daily_division_stats. 본사/계열사/기타 구분 일자별 식수."""

    __tablename__ = "daily_division_stats"
    __table_args__ = (UniqueConstraint("stat_date", "division", "meal_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stat_date: Mapped[dt.date] = mapped_column(Date, index=True)
    division: Mapped[Division] = mapped_column(
        SAEnum(Division, values_callable=lambda e: [x.value for x in e], native_enum=False)
    )
    meal_type: Mapped[MealType] = _meal_type_col()
    headcount: Mapped[int] = mapped_column(Integer, default=0)
    is_holiday: Mapped[bool] = mapped_column(default=False)


class EmployeeTasteProfile(Base):
    """PRD 4.2 / 6.1 employee_taste_profile. food_vector와 동일 차원으로 배치 갱신."""

    __tablename__ = "employee_taste_profile"

    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employee_master.employee_id"), primary_key=True
    )
    profile_vector: Mapped[list[float]] = mapped_column(Vector(FOOD_VECTOR_DIM))
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    # 이 사번이 가장 최근 취향 군집 배치에서 속한 그룹 (app/services/taste_clustering.py)
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("taste_cluster.id", ondelete="SET NULL"), nullable=True
    )


class TasteCluster(Base):
    """PRD 6.1: employee_taste_profile.profile_vector를 K-means로 묶은 취향 군집 요약.

    재계산 배치가 돌 때마다 기존 행을 지우고 새로 쓴다(monthly_voe_cluster와 동일
    패턴) — cluster_index는 그 배치 내에서만 의미가 있고 배치마다 재배정된다.
    """

    __tablename__ = "taste_cluster"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    cluster_index: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(Integer, default=0)
    centroid_vector: Mapped[list[float]] = mapped_column(Vector(FOOD_VECTOR_DIM))
    avg_satisfaction: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_menus: Mapped[list[str] | None] = mapped_column(ARRAY(String(128)), nullable=True)
    dominant_corner: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MonthlyVoeCluster(Base):
    """PRD 4.2 / 5.2 monthly_voe_cluster. 사내 LLM으로 주관식 의견을 월별 군집화한 결과."""

    __tablename__ = "monthly_voe_cluster"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[dt.date] = mapped_column(Date, index=True)  # 매월 1일로 저장
    cluster_label: Mapped[str] = mapped_column(String(128))
    representative_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    keywords: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)), nullable=True)


class CongestionForecast(Base):
    """PRD 4.2 / 7 congestion_forecast. 시뮬레이션 탭과 공유하는 혼잡도 예측 결과."""

    __tablename__ = "congestion_forecast"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    forecast_date: Mapped[dt.date] = mapped_column(Date, index=True)
    corner_id: Mapped[int] = mapped_column(ForeignKey("corner_master.corner_id"), index=True)
    meal_type: Mapped[MealType] = _meal_type_col()
    time_bucket: Mapped[str] = mapped_column(String(16))  # 예: "11:40-11:50"
    predicted_headcount: Mapped[float] = mapped_column(Float)
    predicted_wait_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    # PRD 7.1/7.2: what-if 시나리오 태그. 기본값은 "baseline"(시뮬레이션 미적용 예측).
    scenario_tag: Mapped[str] = mapped_column(String(64), default="baseline")


class MenuPerformanceStats(Base):
    """PRD 4.2 / 6.3 menu_performance_stats. 기간별 메뉴 성과(만족도/빈도/점유율/4분면)."""

    __tablename__ = "menu_performance_stats"
    __table_args__ = (UniqueConstraint("period_start", "period_end", "menu_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_start: Mapped[dt.date] = mapped_column(Date, index=True)
    period_end: Mapped[dt.date] = mapped_column(Date, index=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menu_master.menu_id"), index=True)
    appearance_count: Mapped[int] = mapped_column(Integer, default=0)
    total_headcount: Mapped[int] = mapped_column(Integer, default=0)
    evaluation_count: Mapped[int] = mapped_column(Integer, default=0)
    evaluation_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjusted_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # PRD 6.3.3: 같은 기간 전체 식수 대비 이 메뉴의 점유율 (전체 트래픽 변동 통제용)
    share_of_traffic: Mapped[float | None] = mapped_column(Float, nullable=True)
    quadrant_label: Mapped[MenuQuadrant | None] = mapped_column(
        SAEnum(MenuQuadrant, values_callable=lambda e: [x.value for x in e], native_enum=False),
        nullable=True,
    )
