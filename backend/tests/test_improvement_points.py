import pytest

from app.config import Settings
from app.services.improvement_points import (
    PriorityFinding,
    _find_congestion_finding,
    _find_planning_finding,
    _find_satisfaction_finding,
    _find_voe_finding,
    _fallback_priority_result,
    collect_planning_issues,
    select_priority_finding,
    summarize_priority_finding,
    summarize_voe_comments,
)
from app.services.llm_client import InternalLLMClient


def test_find_satisfaction_finding_picks_worst_needs_improvement_menu():
    menu_rows = [
        {"menu_name": "A", "corner_name": "한식", "quadrant": "개선시급", "share_of_traffic": 0.05, "adjusted_score": 2.8, "evaluation_count": 20},
        {"menu_name": "B", "corner_name": "일품", "quadrant": "개선시급", "share_of_traffic": 0.2, "adjusted_score": 2.5, "evaluation_count": 30},
        {"menu_name": "C", "corner_name": "한식", "quadrant": "인기메뉴", "share_of_traffic": 0.5, "adjusted_score": 4.5, "evaluation_count": 40},
    ]
    finding = _find_satisfaction_finding([], menu_rows)
    assert finding is not None
    assert finding.axis == "satisfaction"
    assert "B" in finding.subject
    assert "2.50" in finding.evidence


def test_find_satisfaction_finding_falls_back_to_corner_when_no_needs_improvement_menu():
    corners = [
        {"corner_name": "한식", "headcount_total": 500, "avg_taste_score": 3.0},
        {"corner_name": "일품", "headcount_total": 480, "avg_taste_score": 4.5},
    ]
    finding = _find_satisfaction_finding(corners, [])
    assert finding is not None
    assert finding.axis == "satisfaction"
    assert "한식" in finding.subject


def test_find_satisfaction_finding_none_when_no_signal():
    assert _find_satisfaction_finding([], []) is None
    corners = [
        {"corner_name": "한식", "headcount_total": 500, "avg_taste_score": 4.0},
        {"corner_name": "일품", "headcount_total": 10, "avg_taste_score": 3.9},
    ]
    # 저조 코너(일품)가 있지만 식수가 median 미만이라 표본 신뢰도 게이트에 걸려 제외된다.
    assert _find_satisfaction_finding(corners, []) is None


def test_find_voe_finding_prefers_largest_month_over_month_increase():
    current = {"categories": [{"category": "맛", "count": 5}, {"category": "위생", "count": 12}, {"category": "기타", "count": 20}]}
    prior = {"categories": [{"category": "맛", "count": 4}, {"category": "위생", "count": 3}]}
    finding = _find_voe_finding(current, prior)
    assert finding is not None
    assert "위생" in finding.subject
    assert "9건" in finding.evidence
    assert finding.voe_category == "위생"


def test_find_voe_finding_falls_back_to_top_count_without_prior_month():
    current = {"categories": [{"category": "맛", "count": 3}, {"category": "위생", "count": 8}]}
    finding = _find_voe_finding(current, None)
    assert finding is not None
    assert "위생" in finding.subject


def test_find_voe_finding_ignores_single_comment_categories():
    # "특정 의견 1건만으로 우선순위를 높이지 않는다" — count가 1건뿐이면 후보에서 빠진다.
    current = {"categories": [{"category": "맛", "count": 1}]}
    assert _find_voe_finding(current, None) is None


def test_find_voe_finding_none_when_no_comments():
    assert _find_voe_finding({"categories": []}, None) is None


def test_collect_planning_issues_is_empty_when_nothing_wrong():
    assert collect_planning_issues(overused=[], no_intake_menus=[], clash_slot_count=0) == []


def test_collect_planning_issues_mentions_each_signal():
    issues = collect_planning_issues(
        overused=[{"menu_name": "김치", "count": 4}],
        no_intake_menus=[{"menu_name": "아무도안먹은메뉴"}],
        clash_slot_count=2,
    )
    assert len(issues) == 3
    assert any("김치" in i for i in issues)
    assert any("표기 불일치" in i for i in issues)
    assert any("2건" in i for i in issues)


def test_find_planning_finding_none_without_issues():
    assert _find_planning_finding([]) is None


def test_find_planning_finding_joins_issues_as_evidence():
    finding = _find_planning_finding(["A", "B"])
    assert finding is not None
    assert finding.axis == "planning"
    assert "A" in finding.evidence and "B" in finding.evidence


def test_find_congestion_finding_flags_high_traffic_low_throughput_corner():
    corners = [
        {"corner_name": "한식", "headcount_total": 500, "avg_peak_throughput_per_min": 0.5},
        {"corner_name": "일품", "headcount_total": 480, "avg_peak_throughput_per_min": 3.0},
        {"corner_name": "분식", "headcount_total": 50, "avg_peak_throughput_per_min": 5.0},
    ]
    finding = _find_congestion_finding(corners)
    assert finding is not None
    assert finding.axis == "congestion"
    assert "한식" in finding.subject


def test_find_congestion_finding_empty_when_not_enough_data():
    assert _find_congestion_finding([{"corner_name": "한식", "headcount_total": 10, "avg_peak_throughput_per_min": 1.0}]) is None
    assert _find_congestion_finding([]) is None


def test_select_priority_finding_cascades_by_priority():
    # 만족도(1순위) 이슈가 있으면 VOE/편성/혼잡도는 아예 검토되지 않는다 — 하나만 반환.
    menu_rows = [
        {"menu_name": "A", "corner_name": "한식", "quadrant": "개선시급", "share_of_traffic": 0.2, "adjusted_score": 2.5, "evaluation_count": 20},
    ]
    corners = [
        {"corner_name": "한식", "headcount_total": 500, "avg_peak_throughput_per_min": 0.5, "avg_taste_score": 3.0},
        {"corner_name": "일품", "headcount_total": 480, "avg_peak_throughput_per_min": 3.0, "avg_taste_score": 4.0},
    ]
    finding = select_priority_finding(
        corners=corners,
        menu_rows=menu_rows,
        current_voe={"categories": [{"category": "위생", "count": 10}]},
        prior_voe=None,
        planning_issues=["문제"],
    )
    assert finding is not None
    assert finding.axis == "satisfaction"


def test_select_priority_finding_falls_through_to_congestion_when_nothing_else():
    corners = [
        {"corner_name": "한식", "headcount_total": 500, "avg_peak_throughput_per_min": 0.5, "avg_taste_score": 4.0},
        {"corner_name": "일품", "headcount_total": 480, "avg_peak_throughput_per_min": 3.0, "avg_taste_score": 4.1},
    ]
    finding = select_priority_finding(
        corners=corners, menu_rows=[], current_voe={"categories": []}, prior_voe=None, planning_issues=[]
    )
    assert finding is not None
    assert finding.axis == "congestion"


def test_select_priority_finding_none_when_no_signal_anywhere():
    corners = [
        {"corner_name": "한식", "headcount_total": 500, "avg_peak_throughput_per_min": 3.0, "avg_taste_score": 4.0},
        {"corner_name": "일품", "headcount_total": 480, "avg_peak_throughput_per_min": 3.0, "avg_taste_score": 4.05},
    ]
    finding = select_priority_finding(
        corners=corners, menu_rows=[], current_voe={"categories": []}, prior_voe=None, planning_issues=[]
    )
    assert finding is None


def test_fallback_priority_result_matches_required_format_fields():
    finding = PriorityFinding(
        axis="congestion", subject="한식 코너", evidence="근거 문장", direction_hint="개선 방향 문장"
    )
    result = _fallback_priority_result(finding)
    assert result["area"] == "혼잡도"
    assert "한식 코너" in result["point"]
    assert result["evidence"] == "근거 문장"
    assert result["direction"] == "개선 방향 문장"


@pytest.mark.asyncio
async def test_summarize_priority_finding_uses_fallback_when_llm_unconfigured():
    llm_client = InternalLLMClient(Settings(internal_llm_base_url=""))
    finding = PriorityFinding(axis="voe", subject="'위생' 관련 의견", evidence="근거", direction_hint="방향")
    result = await summarize_priority_finding(llm_client, finding)
    assert result["area"] == "VOE"
    assert result["evidence"] == "근거"


@pytest.mark.asyncio
async def test_summarize_priority_finding_falls_back_when_llm_call_raises(monkeypatch):
    llm_client = InternalLLMClient(Settings(internal_llm_base_url="http://unreachable.invalid"))

    async def _raise(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr(llm_client, "chat_complete", _raise)
    finding = PriorityFinding(axis="planning", subject="주간 메뉴 편성", evidence="근거", direction_hint="방향")
    result = await summarize_priority_finding(llm_client, finding)
    assert result["evidence"] == "근거"


@pytest.mark.asyncio
async def test_summarize_voe_comments_returns_none_without_comments():
    llm_client = InternalLLMClient(Settings())
    assert await summarize_voe_comments(llm_client, "위생", []) is None


@pytest.mark.asyncio
async def test_summarize_voe_comments_falls_back_to_sample_quote_when_llm_unconfigured():
    llm_client = InternalLLMClient(Settings(internal_llm_base_url=""))
    summary = await summarize_voe_comments(llm_client, "위생", ["위생이 너무 안 좋아요"])
    assert "위생" in summary
    assert "위생이 너무 안 좋아요" in summary


@pytest.mark.asyncio
async def test_summarize_voe_comments_falls_back_when_llm_call_raises(monkeypatch):
    # 사내 LLM은 설정돼 있지만(is_configured=True) 게이트웨이가 타임아웃/연결실패/
    # 오류응답을 내는 상황 — 예외가 카드 전체를 500으로 죽이지 않고 원문 예시
    # 폴백으로 조용히 대체돼야 한다(2026-08 신고 수정 회귀 테스트).
    llm_client = InternalLLMClient(Settings(internal_llm_base_url="http://unreachable.invalid"))

    async def _raise(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr(llm_client, "chat_complete", _raise)
    summary = await summarize_voe_comments(llm_client, "위생", ["위생이 너무 안 좋아요"])
    assert "위생" in summary
    assert "위생이 너무 안 좋아요" in summary
