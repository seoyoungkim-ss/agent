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

from app.models.enums import TASTE_SCORE_POINTS, MenuQuadrant, TasteScore, TrendDirection

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


_DEFAULT_FLAT_TOLERANCE = 0.05  # ±5% 이내 변화는 "유지"로 취급


def compute_trend(
    previous: float | None, current: float | None, *, flat_tolerance: float = _DEFAULT_FLAT_TOLERANCE
) -> TrendDirection:
    """순수 함수 — 이전/현재 값(만족도든 점유율이든)을 비교해 상승/유지/하락 판정.

    4분면 분류(classify_menu_quadrant)가 만족도 추세에 직접 의존하게 되어(2026-07)
    aggregation.py의 private _trend를 이 pure-function 모듈로 옮겼다 — 점유율
    추세(diagnose_headcount_decline)에도 그대로 재사용한다.
    """
    if previous is None or current is None or previous == 0:
        return TrendDirection.FLAT
    change = (current - previous) / previous
    if change <= -flat_tolerance:
        return TrendDirection.DOWN
    if change >= flat_tolerance:
        return TrendDirection.UP
    return TrendDirection.FLAT


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
# 6.3.5 메뉴 로열티 (그 메뉴가 나올 때마다 챙겨 먹는 고정 고객)
# ---------------------------------------------------------------------------

# 코너 코어층(corner_core_layer.py::classify_corner_core_layer)은 "전체 방문
# 대비 이 코너 비중"으로 로열티를 재지만, 메뉴는 코너와 달리 가끔만 나오므로
# (예: 180일 중 3~5번) 같은 방식을 쓰면 비중이 항상 작게 나와 아무도 로열티로
# 안 잡힌다 — 대신 "그 메뉴가 나온 횟수 대비 실제로 주문한 비율"로 잰다
# (2026-07 사용자 결정).


@dataclass(frozen=True)
class MenuLoyaltyResult:
    employee_id: str
    menu_order_count: int
    menu_appearance_count: int
    order_ratio: float


def classify_menu_loyalty(
    employee_menu_counts: dict[str, dict[int, int]],
    menu_id: int,
    menu_appearance_count: int,
    *,
    min_order_count: int = 2,
    min_order_ratio: float = 0.5,
) -> list[MenuLoyaltyResult]:
    """순수 함수 — employee_menu_counts는 {사번: {menu_id: 주문횟수}}.

    코너 코어층(classify_corner_core_layer)과 같은 이중 임계값 구조(절대 횟수
    AND 비율)이지만, 비율의 분모가 "그 사람 전체 식사"가 아니라 "그 메뉴가
    나온 횟수"다.
    """
    if menu_appearance_count <= 0:
        return []
    results = []
    for emp, counts in employee_menu_counts.items():
        order_count = counts.get(menu_id, 0)
        if order_count < min_order_count:
            continue
        ratio = order_count / menu_appearance_count
        if ratio < min_order_ratio:
            continue
        results.append(MenuLoyaltyResult(emp, order_count, menu_appearance_count, ratio))
    results.sort(key=lambda r: (r.order_ratio, r.menu_order_count), reverse=True)
    return results


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
    satisfaction_trend: TrendDirection,
    has_loyal_following: bool,
) -> MenuQuadrant:
    """PRD 6.3.4.

    demand/satisfaction_threshold는 보통 전체 메뉴의 중앙값을 사용한다(호출부 책임).
    표본(evaluation_count)이 부족하면 4분면 판정 대신 LOW_SAMPLE로 별도 표시한다.

    2026-07 확장: (1) 만족도가 기준 이상이어도 직전 대비 하락 중(satisfaction_
    trend=DOWN)이면 "양호"로 인정하지 않는다 — 개선시급/퇴출후보가 기준선
    아래로 떨어지기 전에 하락 추세도 조기에 포착하게 한다. (2) 식수(수요)가
    낮아도 그 메뉴가 나올 때마다 챙겨 먹는 고정 고객이 있으면(has_loyal_
    following) 퇴출후보로 몰지 않고 숨은강자로 본다 — 이 신호가 만족도보다
    우선한다.
    """
    if evaluation_count < low_sample_threshold:
        return MenuQuadrant.LOW_SAMPLE

    high_demand = demand >= demand_threshold
    satisfaction_ok = satisfaction >= satisfaction_threshold and satisfaction_trend != TrendDirection.DOWN

    if high_demand:
        return MenuQuadrant.POPULAR if satisfaction_ok else MenuQuadrant.NEEDS_IMPROVEMENT
    if has_loyal_following:
        return MenuQuadrant.HIDDEN_GEM
    return MenuQuadrant.HIDDEN_GEM if satisfaction_ok else MenuQuadrant.REMOVAL_CANDIDATE
