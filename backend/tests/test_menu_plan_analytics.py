from app.services.menu_plan_analytics import (
    PlanningAction,
    classify_planning_action,
    compute_repertoire,
    median_or_zero,
)


def _classify(plan_count, satisfaction, evaluations=10, headcount=100, **kw):
    return classify_planning_action(
        plan_count,
        satisfaction,
        evaluations,
        headcount,
        median_plan_count=kw.get("median_plan_count", 5),
        median_satisfaction=kw.get("median_satisfaction", 3.5),
        min_evaluations=kw.get("min_evaluations", 5),
    )


# ---------------------------------------------------------------------------
# 편성 조정 판정
# ---------------------------------------------------------------------------


def test_frequent_but_disliked_is_reduce():
    assert _classify(plan_count=10, satisfaction=3.0) == PlanningAction.REDUCE


def test_rare_but_liked_is_increase():
    assert _classify(plan_count=2, satisfaction=4.5) == PlanningAction.INCREASE


def test_frequent_and_liked_is_keep():
    assert _classify(plan_count=10, satisfaction=4.5) == PlanningAction.KEEP


def test_rare_and_disliked_is_as_is():
    assert _classify(plan_count=2, satisfaction=3.0) == PlanningAction.AS_IS


def test_boundary_counts_as_frequent_and_liked():
    """중앙값과 같은 값은 '자주'·'높음' 쪽에 넣는다(>= 기준)."""
    assert _classify(plan_count=5, satisfaction=3.5) == PlanningAction.KEEP


def test_no_intake_wins_over_everything():
    """편성됐는데 취식이 0이면 만족도 비교 자체가 성립하지 않는다."""
    assert _classify(plan_count=10, satisfaction=None, evaluations=0, headcount=0) == (
        PlanningAction.NO_INTAKE
    )
    # 취식이 0이면 평가가 있는 것처럼 들어와도 취식 없음이 우선이다
    assert _classify(plan_count=10, satisfaction=4.5, evaluations=99, headcount=0) == (
        PlanningAction.NO_INTAKE
    )


def test_low_sample_wins_over_quadrant():
    """평가가 적으면 4분면 판정보다 표본 부족이 우선 — 섣불리 감편하면 안 된다."""
    assert _classify(plan_count=10, satisfaction=3.0, evaluations=2) == (
        PlanningAction.LOW_SAMPLE
    )
    assert _classify(plan_count=10, satisfaction=None, evaluations=0) == (
        PlanningAction.LOW_SAMPLE
    )


def test_median_or_zero_handles_empty():
    assert median_or_zero([]) == 0.0
    assert median_or_zero([1.0, 3.0, 5.0]) == 3.0


# ---------------------------------------------------------------------------
# 레퍼토리 집중도
# ---------------------------------------------------------------------------


def test_repertoire_empty_input():
    stats = compute_repertoire({})
    assert stats.total_slots == 0
    assert stats.unique_menus == 0
    assert stats.top_menus == []


def test_repertoire_counts_slots_and_unique_menus():
    stats = compute_repertoire({"돈까스": 3, "김치찌개": 2, "제육볶음": 1})
    assert stats.total_slots == 6
    assert stats.unique_menus == 3
    assert stats.top_menus[0] == ("돈까스", 3)


def test_hhi_discriminates_where_unique_count_and_top_share_cannot():
    """지표를 여러 개 내는 이유 — 하나만 보면 오진한다.

    종수가 top_n 이하면 top_share는 무조건 1.0이라 아무것도 구분 못 한다.
    바로 그 구간을 HHI가 잡는다.
    """
    even = compute_repertoire({"A": 5, "B": 5, "C": 5, "D": 5})  # 4종, 완전히 고르게
    skewed = compute_repertoire({"A": 91, **{chr(ord("B") + i): 1 for i in range(9)}})  # 10종, 쏠림

    assert even.unique_menus < skewed.unique_menus  # 종수만 보면 even이 더 단조로워 보이고
    assert even.top_share == 1.0  # top_share는 종수 ≤ top_n이라 판별력이 없다
    assert even.hhi < skewed.hhi  # 실제 집중도는 even이 훨씬 낮다 — HHI만 이걸 잡는다


def test_top_share_discriminates_when_menu_count_is_large():
    """반대로 종수가 충분히 많으면 top_share가 쏠림을 직관적으로 보여준다."""
    even = compute_repertoire({chr(ord("A") + i): 5 for i in range(20)})
    skewed = compute_repertoire({"A": 91, **{chr(ord("B") + i): 1 for i in range(19)}})
    assert even.top_share < skewed.top_share


def test_top_share_is_one_when_all_menus_fit_in_top_n():
    stats = compute_repertoire({"A": 2, "B": 1}, top_n=5)
    assert stats.top_share == 1.0


def test_repertoire_breaks_count_ties_by_menu_name():
    """동점일 때 순서가 흔들리면 화면이 새로고침마다 바뀐다."""
    stats = compute_repertoire({"나": 2, "가": 2, "다": 2}, top_n=3)
    assert [name for name, _ in stats.top_menus] == ["가", "나", "다"]
