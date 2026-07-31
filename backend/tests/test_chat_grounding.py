import datetime as dt

import app.api.chat as chat_module
from app.models.enums import MealType
from app.models.master import CornerMaster
from app.models.stats import DailyCornerStats
from app.services.chat_grounding import build_grounded_context, route_categories


def test_route_categories_matches_congestion_keyword():
    assert route_categories("오늘 점심 혼잡한가요?") == ["congestion"]


def test_route_categories_matches_multiple_categories():
    categories = route_categories("혼잡하고 만족도도 낮은 코너 알려줘")
    assert set(categories) == {"congestion", "satisfaction"}


def test_route_categories_matches_headcount_keyword():
    assert route_categories("이번주 식수 몇명이야?") == ["headcount"]


def test_route_categories_matches_voe_keyword():
    assert route_categories("최근 VOE 의견 뭐가 많아?") == ["voe"]


def test_route_categories_matches_new_menu_keyword():
    assert route_categories("이번에 나온 신메뉴 반응 어때?") == ["new_menu"]


def test_route_categories_no_match_returns_empty():
    assert route_categories("오늘 날씨 어때?") == []


def test_build_grounded_context_no_match_uses_default_summary(db_session):
    context = build_grounded_context(db_session, "오늘 날씨 어때?")
    assert "최근 7일 식수 상위" in context
    assert "VOE 상위 카테고리" in context


def test_build_grounded_context_satisfaction_includes_real_corner_data(db_session):
    corner = CornerMaster(corner_name="한식")
    db_session.add(corner)
    db_session.flush()
    db_session.add(
        DailyCornerStats(
            stat_date=dt.date.today() - dt.timedelta(days=1),
            corner_id=corner.corner_id,
            meal_type=MealType.LUNCH,
            headcount=42,
            avg_taste_score=4.5,
        )
    )
    db_session.commit()

    context = build_grounded_context(db_session, "코너별 만족도 어때?")
    assert "한식" in context
    assert "4.50" in context
    assert "데이터에 없는 내용은 추측" in context


def test_build_grounded_context_voe_reports_no_data_when_empty(db_session):
    context = build_grounded_context(db_session, "요즘 VOE 불만 많아?")
    assert "데이터 없음" in context


def test_chat_stream_injects_grounded_context_as_system_message(client, monkeypatch):
    captured: dict = {}

    async def fake_chat_stream(self, messages):
        captured["messages"] = messages
        yield "ok"

    monkeypatch.setattr(chat_module.InternalLLMClient, "chat_stream", fake_chat_stream)

    response = client.post(
        "/api/chat/stream",
        json={"messages": [{"role": "user", "content": "이번주 식수 몇명이야?"}]},
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert "이번 주 일자별 식수" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "이번주 식수 몇명이야?"}
