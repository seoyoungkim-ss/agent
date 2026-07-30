import datetime as dt

import pytest

from app.config import get_settings
from app.models.enums import MenuRole
from app.services.weekly_menu_role_llm import _parse_role_response, reclassify_weekly_menu_roles

AUTH_HEADERS = {"Authorization": f"Bearer {get_settings().ingest_api_token}"}
MONDAY = dt.date(2026, 7, 20)


class _FakeLlmClient:
    """chat_complete만 있으면 되는 최소 스텁 — 실제 HTTP 없이 정해진 응답만 돌려준다."""

    def __init__(self, response: str):
        self._response = response

    async def chat_complete(self, messages):
        return self._response


def test_parses_main_and_sides_from_well_formed_response():
    response = "메인: 제육볶음\n부찬: 계란찜, 김치"
    result = _parse_role_response(response, ["제육볶음", "계란찜", "김치"])
    assert result == {"제육볶음": MenuRole.MAIN, "계란찜": MenuRole.SIDE, "김치": MenuRole.SIDE}


def test_returns_none_when_more_than_one_main():
    response = "메인: 제육볶음, 계란찜\n부찬: 김치"
    assert _parse_role_response(response, ["제육볶음", "계란찜", "김치"]) is None


def test_returns_none_when_menu_name_missing_from_response():
    response = "메인: 제육볶음\n부찬: 계란찜"
    # "김치"가 응답에 안 나옴 — 신뢰 못 함
    assert _parse_role_response(response, ["제육볶음", "계란찜", "김치"]) is None


def test_returns_none_when_no_main_line():
    assert _parse_role_response("형식이 이상한 응답입니다", ["제육볶음", "계란찜"]) is None


def _ingest_weekly_menu(client):
    rows = [
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
    resp = client.post("/api/ingest/weekly-menu", json={"rows": rows}, headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_reclassify_updates_role_and_source_when_llm_swaps_them(client, db_session):
    _ingest_weekly_menu(client)  # 규칙 기반: 제육볶음=메인, 계란후라이=부찬

    fake_llm = _FakeLlmClient("메인: 계란후라이\n부찬: 제육볶음")
    reclassified = await reclassify_weekly_menu_roles(db_session, fake_llm, MONDAY, MONDAY)
    assert reclassified == 1

    from app.models.logs import WeeklyMenuPlan

    plans = db_session.query(WeeklyMenuPlan).all()
    by_name = {}
    from app.models.master import MenuMaster

    for plan in plans:
        menu = db_session.get(MenuMaster, plan.menu_id)
        by_name[menu.menu_name] = plan

    assert by_name["계란후라이"].menu_role.value == "메인"
    assert by_name["계란후라이"].role_source.value == "LLM추정"
    assert by_name["제육볶음"].menu_role.value == "부찬"
    assert by_name["제육볶음"].role_source.value == "LLM추정"


@pytest.mark.asyncio
async def test_reclassify_skips_manually_locked_rows(client, db_session):
    _ingest_weekly_menu(client)

    from app.models.logs import WeeklyMenuPlan
    from app.models.master import MenuMaster

    from app.models.enums import MenuRoleSource

    jeyuk_menu = db_session.query(MenuMaster).filter_by(menu_name="제육볶음").one()
    jeyuk_plan = db_session.query(WeeklyMenuPlan).filter_by(menu_id=jeyuk_menu.menu_id).one()
    jeyuk_plan.role_source = MenuRoleSource.MANUAL
    db_session.commit()

    fake_llm = _FakeLlmClient("메인: 계란후라이\n부찬: 제육볶음")
    reclassified = await reclassify_weekly_menu_roles(db_session, fake_llm, MONDAY, MONDAY)
    # 관리자수동 행(제육볶음)은 애초에 쿼리에서 빠지므로, 남은 계란후라이 혼자
    # 있는 "그룹 크기 1"이 돼 재분류 대상에서 제외된다(재분류엔 최소 2개 필요).
    assert reclassified == 0
    db_session.refresh(jeyuk_plan)
    assert jeyuk_plan.menu_role.value == "메인"
    assert jeyuk_plan.role_source.value == "관리자수동"
