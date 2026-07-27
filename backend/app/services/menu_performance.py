"""PRD 6.3: 메뉴별 성과 분석 — 만족도 스코어링, 빈도, 하락 원인 진단, 4분면 분류.

이 모듈은 순수 함수 위주로 작성해 DB 없이 단위 테스트가 가능하게 한다.
실제 배치 집계(app/services/aggregation.py, 추후 구현)는 meal_log/weekly_menu_plan을
조회해 이 함수들에 필요한 값을 계산한 뒤 menu_performance_stats에 저장한다.
"""

import datetime as dt
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from app.models.enums import TASTE_SCORE_POINTS, MenuQuadrant, TasteScore

# ---------------------------------------------------------------------------
# 6.3.1 만족도 점수화 및 표본 수 보정
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MenuScoreResult:
    evaluation_count: int
    raw_score: float | None
    adjusted_score: float | None
    is_low_sample: bool


def compute_menu_score(
    taste_scores: Sequence[TasteScore],
    *,
    global_avg_score: float,
    shrinkage_m: int,
    low_sample_threshold: int,
) -> MenuScoreResult:
    """PRD 6.3.1.

    adjusted_score = n/(n+m) * raw_score + m/(n+m) * global_avg_score

    n이 0이면 raw_score는 없고(None), adjusted_score는 global_avg_score 그대로
    (표본이 전혀 없으니 전체 평균으로 완전히 수렴) 반환한다.
    """
    n = len(taste_scores)
    if n == 0:
        return MenuScoreResult(
            evaluation_count=0,
            raw_score=None,
            adjusted_score=global_avg_score,
            is_low_sample=True,
        )

    raw = sum(TASTE_SCORE_POINTS[s] for s in taste_scores) / n
    adjusted = (n / (n + shrinkage_m)) * raw + (shrinkage_m / (n + shrinkage_m)) * global_avg_score
    return MenuScoreResult(
        evaluation_count=n,
        raw_score=raw,
        adjusted_score=adjusted,
        is_low_sample=n < low_sample_threshold,
    )


# ---------------------------------------------------------------------------
# 6.3.2 빈도 지표 (6개월 누적 기준)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MenuFrequency:
    appearance_count: int  # 제공된 일수
    total_headcount: int  # 누적 선택 인원
    evaluation_count: int
    evaluation_rate: float | None  # evaluation_count / total_headcount
    avg_recurrence_interval_days: float | None
    last_appearance: dt.date | None


def compute_menu_frequency(
    appearance_dates: Sequence[dt.date],
    *,
    total_headcount: int,
    evaluation_count: int,
) -> MenuFrequency:
    unique_dates = sorted(set(appearance_dates))
    appearance_count = len(unique_dates)

    avg_interval: float | None = None
    if appearance_count >= 2:
        gaps = [
            (unique_dates[i + 1] - unique_dates[i]).days for i in range(appearance_count - 1)
        ]
        avg_interval = statistics.fmean(gaps)

    evaluation_rate = evaluation_count / total_headcount if total_headcount > 0 else None

    return MenuFrequency(
        appearance_count=appearance_count,
        total_headcount=total_headcount,
        evaluation_count=evaluation_count,
        evaluation_rate=evaluation_rate,
        avg_recurrence_interval_days=avg_interval,
        last_appearance=unique_dates[-1] if unique_dates else None,
    )


# ---------------------------------------------------------------------------
# 6.3.3 식수 하락 원인 분해 (점유율 vs 만족도)
# ---------------------------------------------------------------------------


class TrendDirection(str, Enum):
    UP = "상승"
    FLAT = "유지"
    DOWN = "하락"


class DeclineDiagnosis(str, Enum):
    MENU_SATISFACTION_ISSUE = "메뉴 자체 만족도 이슈"  # 점유율↓ + 만족도↓
    SUBSTITUTION_RISK = "경쟁 메뉴 대체 가능성"  # 점유율↓ + 만족도 유지/상승
    EXTERNAL_TRAFFIC_ISSUE = "외부 요인(전체 식수 변동)"  # 점유율 유지/상승 + 만족도 유지/상승
    LATENT_CHURN_RISK = "잠재 이탈 위험"  # 점유율 유지/상승 + 만족도↓


def compute_share_of_traffic(menu_headcount: int, total_headcount: int) -> float | None:
    """PRD 6.3.3: 같은 날·같은 식사구분(또는 코너) 전체 식수 대비 이 메뉴의 비중."""
    if total_headcount <= 0:
        return None
    return menu_headcount / total_headcount


def diagnose_headcount_decline(
    share_trend: TrendDirection, satisfaction_trend: TrendDirection
) -> DeclineDiagnosis:
    """PRD 6.3.3의 2x2 매트릭스."""
    share_down = share_trend == TrendDirection.DOWN
    satisfaction_down = satisfaction_trend == TrendDirection.DOWN

    if share_down and satisfaction_down:
        return DeclineDiagnosis.MENU_SATISFACTION_ISSUE
    if share_down and not satisfaction_down:
        return DeclineDiagnosis.SUBSTITUTION_RISK
    if not share_down and satisfaction_down:
        return DeclineDiagnosis.LATENT_CHURN_RISK
    return DeclineDiagnosis.EXTERNAL_TRAFFIC_ISSUE


# ---------------------------------------------------------------------------
# 6.3.4 메뉴 4분면 매트릭스
# ---------------------------------------------------------------------------


def classify_menu_quadrant(
    *,
    demand: float,
    satisfaction: float,
    demand_threshold: float,
    satisfaction_threshold: float,
    evaluation_count: int,
    low_sample_threshold: int,
) -> MenuQuadrant:
    """PRD 6.3.4.

    demand/satisfaction_threshold는 보통 전체 메뉴의 중앙값을 사용한다(호출부 책임).
    표본(evaluation_count)이 부족하면 4분면 판정 대신 LOW_SAMPLE로 별도 표시한다.
    """
    if evaluation_count < low_sample_threshold:
        return MenuQuadrant.LOW_SAMPLE

    high_demand = demand >= demand_threshold
    high_satisfaction = satisfaction >= satisfaction_threshold

    if high_demand and high_satisfaction:
        return MenuQuadrant.POPULAR
    if high_demand and not high_satisfaction:
        return MenuQuadrant.NEEDS_IMPROVEMENT
    if not high_demand and high_satisfaction:
        return MenuQuadrant.HIDDEN_GEM
    return MenuQuadrant.REMOVAL_CANDIDATE
