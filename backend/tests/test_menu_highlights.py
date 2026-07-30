import datetime as dt

from app.models.enums import TasteScore
from app.services.menu_highlights import (
    compute_menu_satisfaction_trends,
    compute_new_menu_reactions,
    week_start,
)

def test_week_start_returns_monday():
    assert week_start(dt.date(2026, 7, 29)) == dt.date(2026, 7, 27)  # 수요일 -> 그 주 월요일
    assert week_start(dt.date(2026, 7, 27)) == dt.date(2026, 7, 27)  # 이미 월요일


def test_menu_satisfaction_trends_detects_rising_and_falling():
    weekly_scores = {
        1: {  # 메뉴1: 지난 등장 대비 만족도 상승
            dt.date(2026, 7, 6): [TasteScore.NORMAL, TasteScore.NORMAL],
            dt.date(2026, 7, 20): [TasteScore.DELICIOUS, TasteScore.DELICIOUS, TasteScore.DELICIOUS],
        },
        2: {  # 메뉴2: 지난 등장 대비 만족도 하락
            dt.date(2026, 7, 6): [TasteScore.DELICIOUS, TasteScore.DELICIOUS, TasteScore.DELICIOUS],
            dt.date(2026, 7, 20): [TasteScore.NEEDS_IMPROVEMENT, TasteScore.NEEDS_IMPROVEMENT],
        },
        3: {  # 메뉴3: 한 번만 등장 — 비교 대상 아님
            dt.date(2026, 7, 20): [TasteScore.DELICIOUS],
        },
    }
    menu_names = {1: "상승메뉴", 2: "하락메뉴", 3: "신규메뉴"}
    menu_corners = {1: "한식", 2: "일품", 3: "분식"}

    rising, falling = compute_menu_satisfaction_trends(
        weekly_scores, menu_names, menu_corners,
        global_avg_score=3.0, shrinkage_m=5, low_sample_threshold=3, top_n=3,
    )

    assert [e.menu_id for e in rising] == [1]
    assert rising[0].delta > 0
    assert [e.menu_id for e in falling] == [2]
    assert falling[0].delta < 0


def test_menu_satisfaction_trends_limits_to_top_n():
    weekly_scores = {
        i: {
            dt.date(2026, 7, 6): [TasteScore.NORMAL],
            dt.date(2026, 7, 20): [TasteScore.DELICIOUS] * i,  # 메뉴마다 다른 크기로 상승폭 차이
        }
        for i in range(1, 6)
    }
    menu_names = {i: f"메뉴{i}" for i in range(1, 6)}
    menu_corners = {i: "한식" for i in range(1, 6)}

    rising, _falling = compute_menu_satisfaction_trends(
        weekly_scores, menu_names, menu_corners,
        global_avg_score=3.0, shrinkage_m=5, low_sample_threshold=3, top_n=2,
    )
    assert len(rising) == 2


def test_new_menu_reactions_computes_score_per_menu():
    today = dt.date(2026, 7, 29)
    new_menus = {
        10: ("신메뉴A", "한식", dt.date(2026, 7, 27)),  # 2일째
        11: ("신메뉴B", None, dt.date(2026, 7, 15)),  # 14일째
    }
    scores_by_menu = {10: [TasteScore.DELICIOUS, TasteScore.DELICIOUS]}  # 11은 평가 없음

    results = compute_new_menu_reactions(
        new_menus, scores_by_menu, global_avg_score=3.0, shrinkage_m=5, low_sample_threshold=3, today=today
    )
    by_id = {r.menu_id: r for r in results}
    assert by_id[10].evaluation_count == 2
    assert by_id[10].adjusted_score is not None
    assert by_id[10].days_since_introduction == 2
    assert by_id[11].evaluation_count == 0
    assert by_id[11].adjusted_score == 3.0  # 평가 없으면 전역 평균으로 수렴
    assert by_id[11].days_since_introduction == 14
    # 도입일 오름차순(최신 먼저) 정렬
    assert [r.menu_id for r in results] == [10, 11]
