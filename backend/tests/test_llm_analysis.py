"""LLM 배치 분석 — 캐시 조회 규칙과 폴백.

§44의 결론(GET 화면 경로의 LLM 실패가 나머지 축을 죽이면 안 된다)과
§45의 교훈(기간 정확 일치 조회는 배치/화면 기준이 하루만 어긋나도 빈 결과가
된다)을 테스트로 고정한다.
"""

import datetime as dt

import pytest

from app.config import Settings
from app.services.improvement_points import build_planning_point, collect_planning_issues
from app.services.llm_analysis import (
    KIND_MENU_TREND,
    _fallback_menu_trend_summary,
    _fallback_planning_notice,
    get_cached,
    save_analysis,
    summarize_menu_trend,
    summarize_planning_notice,
)
from app.services.llm_client import InternalLLMClient


def _facts(delta: float = 0.24) -> dict:
    return {
        "menu_name": "동태찌개",
        "prior_week": "2026-07-13",
        "recent_week": "2026-08-03",
        "prior_score": 4.03,
        "recent_score": 4.27,
        "delta": delta,
        "prior_month": 7,
        "recent_month": 8,
    }


# ---------------------------------------------------------------------------
# 캐시
# ---------------------------------------------------------------------------


def test_get_cached_returns_latest_regardless_of_period(db_session):
    """기간이 어긋나도 최신 1건이 나와야 한다.

    §45에서 배치는 period_end=어제로 쓰고 화면은 오늘로 조회해 빈 결과가 나는
    문제를 겪었다. 여기서는 (kind, subject_key)로만 찾는다.
    """
    save_analysis(
        db_session,
        kind=KIND_MENU_TREND,
        subject_key="7",
        period_start=dt.date(2026, 2, 1),
        period_end=dt.date(2026, 7, 31),
        summary="예전 분석",
        facts={},
    )
    save_analysis(
        db_session,
        kind=KIND_MENU_TREND,
        subject_key="7",
        period_start=dt.date(2026, 2, 2),
        period_end=dt.date(2026, 8, 5),
        summary="최신 분석",
        facts={},
    )
    cached = get_cached(db_session, KIND_MENU_TREND, "7")
    assert cached is not None
    assert cached.summary == "최신 분석"


def test_get_cached_returns_none_for_unknown_subject(db_session):
    assert get_cached(db_session, KIND_MENU_TREND, "존재하지않음") is None


def test_saved_facts_are_round_trippable(db_session):
    """왜 이런 설명이 나왔는지 나중에 검증할 수 있어야 한다."""
    import json

    row = save_analysis(
        db_session,
        kind=KIND_MENU_TREND,
        subject_key="9",
        period_start=dt.date(2026, 8, 1),
        period_end=dt.date(2026, 8, 5),
        summary="요약",
        facts=_facts(),
    )
    assert json.loads(row.facts_json)["menu_name"] == "동태찌개"


# ---------------------------------------------------------------------------
# 폴백 — LLM 미설정이 정상 동작 경로다
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_menu_trend_falls_back_when_llm_not_configured():
    client = InternalLLMClient(Settings(internal_llm_base_url=""))
    summary = await summarize_menu_trend(client, _facts())
    assert "4.03" in summary and "4.27" in summary
    assert "미설정" in summary  # 모의 응답이 아니라 폴백임이 드러나야 한다


@pytest.mark.asyncio
async def test_menu_trend_falls_back_when_llm_call_raises(monkeypatch):
    """LLM 호출이 터져도 예외가 올라오면 안 된다(§44와 같은 방어)."""
    client = InternalLLMClient(Settings(internal_llm_base_url="http://unreachable.invalid"))

    async def _boom(*_args, **_kwargs):
        raise ConnectionError("사내 LLM 도달 불가")

    monkeypatch.setattr(client, "chat_complete", _boom)
    summary = await summarize_menu_trend(client, _facts())
    assert "4.03" in summary


@pytest.mark.asyncio
async def test_planning_notice_returns_empty_when_no_issues():
    client = InternalLLMClient(Settings(internal_llm_base_url=""))
    assert await summarize_planning_notice(client, {"issues": []}) == ""


def test_fallback_menu_trend_mentions_direction():
    assert "하락" in _fallback_menu_trend_summary(_facts(delta=-0.5))
    assert "상승" in _fallback_menu_trend_summary(_facts(delta=0.5))


def test_fallback_planning_notice_counts_extra_issues():
    text = _fallback_planning_notice({"issues": ["A", "B", "C"]})
    assert "A" in text and "2건" in text


# ---------------------------------------------------------------------------
# 편성 축 사실 수집 (순수 함수)
# ---------------------------------------------------------------------------


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


def test_build_planning_point_is_none_without_issues():
    assert build_planning_point([], None) is None


def test_build_planning_point_uses_llm_summary_when_available():
    point = build_planning_point(["A", "B"], "LLM이 다듬은 한 문장")
    assert point is not None
    assert point.axis == "planning"
    assert point.detail == "LLM이 다듬은 한 문장"


def test_build_planning_point_falls_back_to_raw_facts():
    """LLM 요약이 없으면 사실을 그대로 보여준다 — 빈 카드보다 낫다."""
    point = build_planning_point(["A", "B"], None)
    assert point is not None
    assert "A" in point.detail and "B" in point.detail
