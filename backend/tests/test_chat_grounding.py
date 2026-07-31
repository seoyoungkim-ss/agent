import datetime as dt

import pytest

import app.api.chat as chat_module
from app.models.enums import Division, MealType
from app.models.logs import MealLog
from app.models.master import CornerMaster, EmployeeMaster, MenuMaster
from app.models.stats import DailyCornerStats, DailyDivisionStats
from app.services.chat_grounding import (
    _extract_month_range,
    _extract_top_n,
    _wants_ranking,
    build_grounded_context,
    route_categories,
)


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


def test_route_categories_matches_menu_ranking_keyword():
    assert route_categories("이번 달 가장 많이 먹은 메뉴 뭐야?") == ["menu_ranking"]


def test_route_categories_no_match_returns_empty():
    assert route_categories("오늘 날씨 어때?") == []


def test_extract_month_range_parses_past_month_in_same_year():
    today = dt.date.today()
    if today.month == 1:
        pytest.skip("1월에는 '지난달' 케이스로 커버")
    target_month = today.month - 1
    result = _extract_month_range(f"{target_month}월 식수 알려줘")
    assert result is not None
    start, end = result
    assert start == dt.date(today.year, target_month, 1)
    assert end.month == target_month
    assert end.year == today.year


def test_extract_month_range_rolls_back_year_for_future_month():
    today = dt.date.today()
    if today.month == 12:
        pytest.skip("12월에는 미래 달이 존재하지 않아 테스트 불가")
    future_month = today.month + 1
    result = _extract_month_range(f"{future_month}월 식수")
    assert result is not None
    start, _ = result
    assert start.year == today.year - 1
    assert start.month == future_month


def test_extract_month_range_handles_last_month_keyword():
    today = dt.date.today()
    first_of_this_month = today.replace(day=1)
    expected_end = first_of_this_month - dt.timedelta(days=1)
    result = _extract_month_range("지난달 식수 어땠어?")
    assert result == (expected_end.replace(day=1), expected_end)


def test_extract_month_range_handles_this_month_keyword():
    today = dt.date.today()
    result = _extract_month_range("이번달 식수 어때?")
    assert result == (today.replace(day=1), today)


def test_extract_month_range_no_match_returns_none():
    assert _extract_month_range("오늘 혼잡한 코너 알려줘") is None


def test_extract_top_n_parses_top_n_pattern():
    assert _extract_top_n("6월 식수 top3가 뭐야") == 3


def test_extract_top_n_parses_korean_ranking_pattern():
    assert _extract_top_n("상위 5개만 보여줘") == 5


def test_extract_top_n_default_when_no_number():
    assert _extract_top_n("가장 많이 나온 거 알려줘", default=7) == 7


def test_wants_ranking_true_for_top_keyword():
    assert _wants_ranking("6월 식수 top3가 뭐야") is True


def test_wants_ranking_false_without_ranking_keyword():
    assert _wants_ranking("이번주 식수 몇명이야?") is False


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


def test_build_grounded_context_menu_ranking_lists_top_menus(db_session):
    corner = CornerMaster(corner_name="한식")
    employee = EmployeeMaster(employee_id="E1", division=Division.OTHER)
    menu_a = MenuMaster(menu_name="제육볶음")
    menu_b = MenuMaster(menu_name="돈까스")
    db_session.add_all([corner, employee, menu_a, menu_b])
    db_session.flush()

    today = dt.date.today()
    for i in range(3):
        db_session.add(
            MealLog(
                eaten_at=dt.datetime.combine(today, dt.time(11, i)),
                employee_id="E1",
                meal_type=MealType.LUNCH,
                corner_id=corner.corner_id,
                menu_id=menu_a.menu_id,
            )
        )
    db_session.add(
        MealLog(
            eaten_at=dt.datetime.combine(today, dt.time(12, 0)),
            employee_id="E1",
            meal_type=MealType.LUNCH,
            corner_id=corner.corner_id,
            menu_id=menu_b.menu_id,
        )
    )
    db_session.commit()

    context = build_grounded_context(db_session, "이번달 가장 많이 먹은 메뉴 top2 알려줘")
    assert "제육볶음: 3건" in context
    assert "돈까스: 1건" in context


def test_build_grounded_context_headcount_ranking_sorts_and_limits(db_session):
    today = dt.date.today()
    db_session.add_all(
        [
            DailyDivisionStats(
                stat_date=today,
                division=Division.OTHER,
                meal_type=MealType.LUNCH,
                headcount=10,
            ),
            DailyDivisionStats(
                stat_date=today.replace(day=1),
                division=Division.OTHER,
                meal_type=MealType.LUNCH,
                headcount=99,
            ),
        ]
    )
    db_session.commit()

    context = build_grounded_context(db_session, "이번달 식수 top1 알려줘")
    lines = [line for line in context.splitlines() if line.startswith("- ")]
    assert len(lines) == 1
    assert "99명" in lines[0]


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
