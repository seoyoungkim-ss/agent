"""편성(weekly_menu_plan) 기준 분석 — "다음 주 뭘 빼고 뭘 넣을까" (2026-08).

식단표 8개월치가 적재되면서 처음 가능해진 분석이다. 그전엔 `weekly_menu_plan`이
최근 몇 주치뿐이라 편성 이력 자체를 분석 대상으로 쓸 수 없었다.

**기존 4분면과 축이 다르다.** `menu_performance_stats.appearance_count`는
`meal_log`의 **취식 발생 일수**다(`aggregation.py`의
`[r.eaten_at.date() for r in rows]`). 즉 편성했는데 아무도 안 먹은 메뉴는
`by_menu`에 안 들어와 4분면에서 **아예 사라진다**. 여기선 `weekly_menu_plan`
기준이라 그게 보이고, 그게 가장 강한 감편 신호다.

§80: X축을 "편성 횟수"(plan_count)에서 "1회 편성당 식수"(headcount_per_plan)
로 바꿨다(담당자: "편성 횟수는 불필요") — 판정 기준값도 같이 바꿨다(화면엔
식수 축인데 감편/증편 라벨은 편성 횟수 기준이면 불일치가 생긴다). 취식이
아예 없는 메뉴(감편의 가장 강한 신호)를 여전히 보여주는 이 화면의 원래
목적은 유지된다 — headcount_per_plan도 취식 0이면 0이라 `NO_INTAKE` 판정이
먼저 걸린다.

DB를 모르는 순수 함수만 둔다. 조회는 `app/api/analysis.py`가 맡는다(레포 관례).
"""

import statistics
from enum import Enum

# 평가가 이보다 적으면 만족도를 믿고 편성을 바꾸기 어렵다.
# menu_performance의 low_sample_threshold와 같은 취지지만, 이쪽은 기간이 훨씬
# 길어(6~12개월) 기준을 조금 높게 잡는다.
DEFAULT_MIN_EVALUATIONS = 5


class PlanningAction(str, Enum):
    REDUCE = "감편 검토"  # 자주 편성 + 반응 낮음
    INCREASE = "증편 후보"  # 드물게 편성 + 반응 높음
    KEEP = "주력 유지"  # 자주 + 높음
    AS_IS = "현행 유지"  # 드물게 + 낮음 — 굳이 늘릴 이유가 없다
    LOW_SAMPLE = "표본 부족"  # 평가가 적어 판단 보류
    NO_INTAKE = "취식 기록 없음"  # 편성됐는데 취식이 0 — 이름 불일치일 수도 있다


def classify_planning_action(
    headcount_per_plan: float,
    avg_satisfaction: float | None,
    evaluation_count: int,
    total_headcount: int,
    *,
    median_headcount_per_plan: float,
    median_satisfaction: float,
    min_evaluations: int = DEFAULT_MIN_EVALUATIONS,
) -> PlanningAction:
    """순수 함수 — 1회 편성당 식수와 만족도를 기간 중앙값과 비교해 편성 조정
    방향을 낸다.

    기준선으로 **그 기간 전체의 중앙값**을 쓰는 건 기존 4분면
    (`aggregation.py`의 `demand_values`/`score_values` 중앙값)과 같은 방식이다.
    화면마다 다른 기준을 쓰면 담당자의 판정 감각이 어긋난다.

    판정 우선순위가 중요하다: 취식 0 → 표본 부족 → 4분면. 취식이 아예 없으면
    만족도 비교 자체가 성립하지 않고, "진짜 아무도 안 먹음"과 "메뉴명이 안 맞아
    매칭 실패"가 섞여 있어 별도 판정으로 빼서 담당자가 확인하게 한다.
    """
    if total_headcount == 0:
        return PlanningAction.NO_INTAKE
    if avg_satisfaction is None or evaluation_count < min_evaluations:
        return PlanningAction.LOW_SAMPLE

    high_demand = headcount_per_plan >= median_headcount_per_plan
    liked = avg_satisfaction >= median_satisfaction

    if high_demand and not liked:
        return PlanningAction.REDUCE
    if not high_demand and liked:
        return PlanningAction.INCREASE
    if high_demand and liked:
        return PlanningAction.KEEP
    return PlanningAction.AS_IS


def median_or_zero(values: list[float]) -> float:
    """빈 목록이면 0 — 중앙값 계산에서 예외를 던지지 않게 한다."""
    return statistics.median(values) if values else 0.0
