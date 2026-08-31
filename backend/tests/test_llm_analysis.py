"""LLM 배치 분석 — 캐시 조회 규칙과 폴백.

§44의 결론(GET 화면 경로의 LLM 실패가 나머지 축을 죽이면 안 된다)과
§45의 교훈(기간 정확 일치 조회는 배치/화면 기준이 하루만 어긋나도 빈 결과가
된다)을 테스트로 고정한다.
"""

import datetime as dt

import pytest

from app.config import Settings, get_settings
from app.services.llm_analysis import (
    KIND_MENU_TREND,
    KIND_VOE_BRIEFING,
    _build_menu_trend_prompt,
    _build_voe_briefing_prompt,
    _collect_voe_briefing_facts,
    _fallback_menu_trend_summary,
    _fallback_voe_briefing,
    _recent_comments_for_menu,
    _side_dishes_for_menu_week,
    get_cached,
    save_analysis,
    summarize_menu_trend,
    summarize_voe_briefing,
)
from app.services.llm_client import InternalLLMClient

MONDAY = dt.date(2026, 7, 20)
AUTH_HEADERS = {"Authorization": f"Bearer {get_settings().ingest_api_token}"}


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
    summary, keywords = await summarize_menu_trend(client, _facts())
    assert "4.03" in summary and "4.27" in summary
    assert "미설정" in summary  # 모의 응답이 아니라 폴백임이 드러나야 한다
    assert keywords == []


@pytest.mark.asyncio
async def test_menu_trend_falls_back_when_llm_call_raises(monkeypatch):
    """LLM 호출이 터져도 예외가 올라오면 안 된다(§44와 같은 방어)."""
    client = InternalLLMClient(Settings(internal_llm_base_url="http://unreachable.invalid"))

    async def _boom(*_args, **_kwargs):
        raise ConnectionError("사내 LLM 도달 불가")

    monkeypatch.setattr(client, "chat_complete", _boom)
    summary, keywords = await summarize_menu_trend(client, _facts())
    assert "4.03" in summary
    assert keywords == []


@pytest.mark.asyncio
async def test_menu_trend_parses_keywords_from_last_line(monkeypatch):
    client = InternalLLMClient(Settings(internal_llm_base_url="http://unreachable.invalid"))

    async def _fake_reply(*_args, **_kwargs):
        return "짠맛이 강해졌다는 의견이 많았습니다.\n키워드: 짠맛, 간, 양"

    monkeypatch.setattr(client, "chat_complete", _fake_reply)
    summary, keywords = await summarize_menu_trend(client, _facts())
    assert "짠맛이 강해졌다" in summary
    assert "키워드:" not in summary
    assert keywords == ["짠맛", "간", "양"]


@pytest.mark.asyncio
async def test_menu_trend_keywords_empty_when_response_has_no_keyword_line(monkeypatch):
    client = InternalLLMClient(Settings(internal_llm_base_url="http://unreachable.invalid"))

    async def _fake_reply(*_args, **_kwargs):
        return "뚜렷한 원인을 특정하기 어렵습니다."

    monkeypatch.setattr(client, "chat_complete", _fake_reply)
    summary, keywords = await summarize_menu_trend(client, _facts())
    assert "특정하기 어렵습니다" in summary
    assert keywords == []


def test_fallback_menu_trend_mentions_direction():
    assert "하락" in _fallback_menu_trend_summary(_facts(delta=-0.5))
    assert "상승" in _fallback_menu_trend_summary(_facts(delta=0.5))


# ---------------------------------------------------------------------------
# 편성 축 사실 수집(`collect_planning_issues`)과 편성 이슈 판정/문구 다듬기는
# §109부터 improvement_points.py로 통합돼 test_improvement_points.py에서
# 검증한다 — 여기서는 메뉴 만족도 원인/VOE 브리핑만 다룬다.
# ---------------------------------------------------------------------------
# §77: 하이라이트 프롬프트 — 실제 코멘트 + 부찬 조합 배선
#
# 이전엔 prior_sides/recent_sides/competing_menus가 프롬프트에서만 기대되고
# 한 번도 채워진 적이 없어(refresh_llm_analyses가 6개 필드만 넘김) LLM이 늘
# "특정하기 어렵다"고만 답했다. 실제 코멘트를 근거로 주면 프롬프트에 반영되고,
# 새 fact-수집 헬퍼 두 개가 DB에서 정확히 가져오는지 확인한다.
# ---------------------------------------------------------------------------


def test_build_menu_trend_prompt_includes_comments_when_present():
    facts = _facts()
    facts["recent_comments"] = ["짜서 별로였어요", "양이 줄었어요"]
    facts["prior_comments"] = []
    prompt = _build_menu_trend_prompt(facts)
    assert "짜서 별로였어요" in prompt
    assert "양이 줄었어요" in prompt
    assert "최근 주 직원 코멘트:" in prompt
    assert "그 내용을 우선 근거로 삼으세요" in prompt


def test_build_menu_trend_prompt_omits_comment_lines_when_absent():
    prompt = _build_menu_trend_prompt(_facts())
    assert "최근 주 직원 코멘트:" not in prompt
    assert "이전 주 직원 코멘트:" not in prompt


def test_side_dishes_for_menu_week_finds_same_slot_side_menu(client, db_session):
    from app.models.master import MenuMaster

    resp = client.post(
        "/api/ingest/weekly-menu",
        json={
            "rows": [
                {
                    "plan_date": MONDAY.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "한식",
                    "menu_name": "제육볶음",
                    "menu_role": "메인",
                    "source_row_raw": "제육볶음\n계란후라이",
                },
                {
                    "plan_date": MONDAY.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "한식",
                    "menu_name": "계란후라이",
                    "menu_role": "부찬",
                    "source_row_raw": "제육볶음\n계란후라이",
                },
            ]
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    menu = db_session.query(MenuMaster).filter(MenuMaster.menu_name == "제육볶음").one()
    assert _side_dishes_for_menu_week(db_session, menu.menu_id, MONDAY) == "계란후라이"


def test_side_dishes_for_menu_week_returns_none_without_main_slot(db_session):
    assert _side_dishes_for_menu_week(db_session, 99999, MONDAY) is None


def test_recent_comments_for_menu_filters_to_week_range(client, db_session):
    from app.models.master import MenuMaster

    tuesday = MONDAY + dt.timedelta(days=1)
    next_monday = MONDAY + dt.timedelta(days=7)
    rows = [
        {
            "eaten_at": dt.datetime.combine(tuesday, dt.time(11, 50)).isoformat(),
            "employee_id": "E1",
            "meal_type": "중식",
            "corner_name": "한식",
            "taste_score": "맛남",
            "comment": "짜요",
            "menu_name": "동태찌개",
        },
        {
            "eaten_at": dt.datetime.combine(next_monday, dt.time(11, 50)).isoformat(),
            "employee_id": "E2",
            "meal_type": "중식",
            "corner_name": "한식",
            "taste_score": "맛남",
            "comment": "다음주 코멘트",
            "menu_name": "동태찌개",
        },
    ]
    resp = client.post("/api/ingest/meal-log", json={"rows": rows}, headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    menu = db_session.query(MenuMaster).filter(MenuMaster.menu_name == "동태찌개").one()
    assert _recent_comments_for_menu(db_session, menu.menu_id, MONDAY) == ["짜요"]


# ---------------------------------------------------------------------------
# VOE AI 브리핑 (§80) — cluster_monthly_voe가 만든 MonthlyVoeCluster를
# 재사용하는 다중 테마 요약. 재임베딩은 하지 않는다.
# ---------------------------------------------------------------------------


def _voe_facts(*clusters: dict) -> dict:
    return {"month": "2026-08-01", "clusters": list(clusters)}


def _voe_cluster(label="맛 관련", keywords=None, comment="너무 짜요", count=5) -> dict:
    return {
        "label": label,
        "keywords": keywords or ["짜다"],
        "representative_comment": comment,
        "comment_count": count,
    }


def test_collect_voe_briefing_facts_returns_clusters_sorted_by_count(db_session):
    from app.models.stats import MonthlyVoeCluster

    month_start = dt.date(2026, 8, 1)
    db_session.add_all(
        [
            MonthlyVoeCluster(
                period=month_start,
                cluster_label="적음",
                representative_comment="양이 적어요",
                comment_count=2,
                keywords=["양"],
            ),
            MonthlyVoeCluster(
                period=month_start,
                cluster_label="많음",
                representative_comment="자주 나와요",
                comment_count=9,
                keywords=["반복"],
            ),
        ]
    )
    db_session.commit()

    facts = _collect_voe_briefing_facts(db_session, month_start)
    assert facts["month"] == "2026-08-01"
    assert [c["label"] for c in facts["clusters"]] == ["많음", "적음"]


def test_collect_voe_briefing_facts_empty_when_no_clusters(db_session):
    facts = _collect_voe_briefing_facts(db_session, dt.date(2026, 8, 1))
    assert facts["clusters"] == []


def test_collect_voe_briefing_facts_includes_top_corners_and_menus(db_session):
    """2026-08 담당자 요청: "voe가 많았던 코너, 메뉴도 요약에 포함" —
    meal_log를 코너/메뉴로 조인해 그 달 코멘트 건수 상위를 facts에 담는다."""
    from app.models.enums import Division, MealType
    from app.models.logs import MealLog
    from app.models.master import CornerMaster, EmployeeMaster, MenuMaster

    hansik = CornerMaster(corner_name="한식")
    bunsik = CornerMaster(corner_name="분식")
    kimchi = MenuMaster(menu_name="김치찌개")
    employee = EmployeeMaster(employee_id="E1", division=Division.OTHER)
    db_session.add_all([hansik, bunsik, kimchi, employee])
    db_session.flush()

    # 한식 코멘트 2건(그중 1건은 김치찌개), 분식 코멘트 1건 — 코너는 한식이 1위.
    db_session.add_all(
        [
            MealLog(
                eaten_at=dt.datetime(2026, 8, 3, 12, 0),
                employee_id="E1",
                meal_type=MealType.LUNCH,
                corner_id=hansik.corner_id,
                menu_id=kimchi.menu_id,
                comment="국물이 짜요",
            ),
            MealLog(
                eaten_at=dt.datetime(2026, 8, 4, 12, 0),
                employee_id="E1",
                meal_type=MealType.LUNCH,
                corner_id=hansik.corner_id,
                comment="맛있어요",
            ),
            MealLog(
                eaten_at=dt.datetime(2026, 8, 5, 12, 0),
                employee_id="E1",
                meal_type=MealType.LUNCH,
                corner_id=bunsik.corner_id,
                comment="양이 적어요",
            ),
        ]
    )
    db_session.commit()

    facts = _collect_voe_briefing_facts(db_session, dt.date(2026, 8, 1))
    assert facts["top_corners"][0] == {"corner_name": "한식", "comment_count": 2}
    assert {"corner_name": "분식", "comment_count": 1} in facts["top_corners"]
    assert facts["top_menus"] == [{"menu_name": "김치찌개", "comment_count": 1}]

    prompt = _build_voe_briefing_prompt(facts)
    assert "한식(2건)" in prompt
    assert "김치찌개(1건)" in prompt


def test_build_voe_briefing_prompt_includes_cluster_details():
    facts = _voe_facts(_voe_cluster())
    prompt = _build_voe_briefing_prompt(facts)
    assert "맛 관련" in prompt
    assert "너무 짜요" in prompt
    assert "5건" in prompt
    assert "지어내지 마세요" in prompt


def test_fallback_voe_briefing_lists_clusters_when_present():
    facts = _voe_facts(_voe_cluster(label="맛", count=3), _voe_cluster(label="위생", count=1))
    summary = _fallback_voe_briefing(facts)
    assert "맛(3건)" in summary
    assert "위생(1건)" in summary
    assert "미설정" in summary


def test_fallback_voe_briefing_when_no_clusters():
    assert _fallback_voe_briefing(_voe_facts()) == "이번 달 주관식 의견이 없습니다."


@pytest.mark.asyncio
async def test_summarize_voe_briefing_falls_back_when_llm_not_configured():
    client = InternalLLMClient(Settings(internal_llm_base_url=""))
    summary = await summarize_voe_briefing(client, _voe_facts(_voe_cluster()))
    assert "맛 관련(5건)" in summary


@pytest.mark.asyncio
async def test_summarize_voe_briefing_falls_back_without_clusters_even_if_llm_configured():
    client = InternalLLMClient(Settings(internal_llm_base_url="http://unreachable.invalid"))
    summary = await summarize_voe_briefing(client, _voe_facts())
    assert summary == "이번 달 주관식 의견이 없습니다."


def test_voe_briefing_cache_round_trips(db_session):
    save_analysis(
        db_session,
        kind=KIND_VOE_BRIEFING,
        subject_key="2026-08-01",
        period_start=dt.date(2026, 8, 1),
        period_end=dt.date(2026, 8, 1),
        summary="이번 달 브리핑",
        facts=_voe_facts(_voe_cluster()),
    )
    cached = get_cached(db_session, KIND_VOE_BRIEFING, "2026-08-01")
    assert cached is not None
    assert cached.summary == "이번 달 브리핑"
