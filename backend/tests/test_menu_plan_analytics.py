from app.services.menu_plan_analytics import (
    PlanningAction,
    classify_planning_action,
    median_or_zero,
)


def _classify(headcount_per_plan, satisfaction, evaluations=10, headcount=100, **kw):
    return classify_planning_action(
        headcount_per_plan,
        satisfaction,
        evaluations,
        headcount,
        median_headcount_per_plan=kw.get("median_headcount_per_plan", 5),
        median_satisfaction=kw.get("median_satisfaction", 3.5),
        min_evaluations=kw.get("min_evaluations", 5),
    )


# ---------------------------------------------------------------------------
# 편성 조정 판정 — §80: X축이 "편성 횟수"에서 "1회 편성당 식수"로 바뀌었다.
# ---------------------------------------------------------------------------


def test_high_demand_but_disliked_is_reduce():
    assert _classify(headcount_per_plan=10, satisfaction=3.0) == PlanningAction.REDUCE


def test_low_demand_but_liked_is_increase():
    assert _classify(headcount_per_plan=2, satisfaction=4.5) == PlanningAction.INCREASE


def test_high_demand_and_liked_is_keep():
    assert _classify(headcount_per_plan=10, satisfaction=4.5) == PlanningAction.KEEP


def test_low_demand_and_disliked_is_as_is():
    assert _classify(headcount_per_plan=2, satisfaction=3.0) == PlanningAction.AS_IS


def test_boundary_counts_as_high_demand_and_liked():
    """중앙값과 같은 값은 '자주'·'높음' 쪽에 넣는다(>= 기준)."""
    assert _classify(headcount_per_plan=5, satisfaction=3.5) == PlanningAction.KEEP


def test_no_intake_wins_over_everything():
    """편성됐는데 취식이 0이면 만족도 비교 자체가 성립하지 않는다."""
    assert _classify(headcount_per_plan=10, satisfaction=None, evaluations=0, headcount=0) == (
        PlanningAction.NO_INTAKE
    )
    # 취식이 0이면 평가가 있는 것처럼 들어와도 취식 없음이 우선이다
    assert _classify(headcount_per_plan=10, satisfaction=4.5, evaluations=99, headcount=0) == (
        PlanningAction.NO_INTAKE
    )


def test_low_sample_wins_over_quadrant():
    """평가가 적으면 4분면 판정보다 표본 부족이 우선 — 섣불리 감편하면 안 된다."""
    assert _classify(headcount_per_plan=10, satisfaction=3.0, evaluations=2) == (
        PlanningAction.LOW_SAMPLE
    )
    assert _classify(headcount_per_plan=10, satisfaction=None, evaluations=0) == (
        PlanningAction.LOW_SAMPLE
    )


def test_median_or_zero_handles_empty():
    assert median_or_zero([]) == 0.0
    assert median_or_zero([1.0, 3.0, 5.0]) == 3.0
