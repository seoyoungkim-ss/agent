import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
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
from app.models.enums import Division, MealType, MenuQuadrant, TrendDirection
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


class DailyWeather(Base):
    """PRD 7.1 daily_weather. 기상청 ASOS 일자료(과거 강수-식수 상관관계 검증용).

    날씨는 코너/구분/끼니와 무관한 날짜 단위 사실이라, daily_corner_stats처럼
    코너별로 중복 저장하지 않고 holiday_calendar와 같이 날짜 하나만 키로 잡는다
    (2026-08) — 같은 날 수십 개 코너 행마다 같은 값을 복제하면 정정 시 N개 행을
    다 고쳐야 하는 문제가 생긴다.
    """

    __tablename__ = "daily_weather"

    stat_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    precip_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    had_rain: Mapped[bool] = mapped_column(Boolean, default=False)
    avg_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    # PRD 7.1 확장(2026-08): 메뉴×날씨유형(폭설/폭염/한파) 랭킹(§71)에 필요해
    # 추가 — ASOS 일자료 응답에 이미 같이 들어있는 필드라 API를 새로 안 붙여도
    # 된다. 기존에 저장된 행들은 이 필드가 NULL이라 재백필 전까진 "비" 분류만
    # 가능하다(운영 안내는 docs/CALCULATION_LOGIC.md §71 참고).
    snow_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "kma_api" | "csv_import" — 사내망이 data.go.kr에 못 닿는 배포는 전량
    # csv_import로 채워질 수 있어 화면/문서에서 출처를 밝히기 위해 남긴다.
    source: Mapped[str] = mapped_column(String(16), default="kma_api")
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)


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
    # PRD 6.3.4 확장(2026-07): 4분면 분류에 쓰인 최근/직전 N일 만족도 추세 —
    # 개선시급/퇴출후보가 "아직 기준 이상이지만 하락 중"인 경우도 잡게 됨.
    satisfaction_trend: Mapped[TrendDirection | None] = mapped_column(
        SAEnum(TrendDirection, values_callable=lambda e: [x.value for x in e], native_enum=False),
        nullable=True,
    )
    # PRD 6.3.5(2026-07): 수요가 낮아도 그 메뉴가 나올 때마다 챙겨 먹는 고정
    # 고객이 있으면 True — 4분면 분류에서 퇴출후보 대신 숨은강자로 보정한다.
    has_loyal_following: Mapped[bool] = mapped_column(Boolean, default=False)


class LlmAnalysisCache(Base):
    """LLM이 만든 설명을 저장해 두는 캐시 (2026-08).

    화면 로드마다 LLM을 부르면 지금도 느린 화면이 더 느려진다(§25의 판단과 동일,
    실사용에서 "로딩되다가 결과가 안 나온다"는 신고까지 나온 뒤라 더 명확하다).
    그래서 새벽 배치가 미리 계산해 여기에 넣고, 화면은 읽기만 한다. 관리자가
    "지금 다시 분석" 버튼으로 갱신할 수도 있다 — voe_clustering과 같은 구조.

    ⚠️ **기간 정확 일치로 조회하지 않는다.** §45에서 menu_performance_stats를
    `filter_by(period_start=..., period_end=...)`로 읽다가, 배치는 `period_end=어제`로
    쓰고 화면은 `period_end=오늘`로 찾아 빈 결과가 나오는 문제를 겪었다. 여기서는
    (kind, subject_key)로 **가장 최근 행 1개**를 읽고, 그 분석이 언제·어느 기간을
    근거로 만들어졌는지를 화면에 함께 보여준다.
    """

    __tablename__ = "llm_analysis_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # "menu_trend"(만족도 변화 원인) | "planning_notice"(편성/운영 문제)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    # menu_trend면 menu_id 문자열, planning_notice면 규칙 식별자
    subject_key: Mapped[str] = mapped_column(String(64), index=True)
    period_start: Mapped[dt.date] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text)
    # LLM에 넘긴 사실 — 나중에 "왜 이런 설명이 나왔나"를 검증할 수 있게 남긴다.
    facts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, index=True)
