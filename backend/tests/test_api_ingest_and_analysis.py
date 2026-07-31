import datetime as dt
import io

import pytest

from app.config import get_settings

AUTH_HEADERS = {"Authorization": f"Bearer {get_settings().ingest_api_token}"}

MONDAY = dt.date(2026, 7, 20)


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
    return resp.json()


def _ingest_meal_log(
    client,
    employee_id: str,
    taste: str,
    comment: str | None = None,
    company_name: str | None = None,
    eaten_date: dt.date = MONDAY,
    menu_name: str | None = None,
    corner_name: str = "한식",
):
    rows = [
        {
            "eaten_at": dt.datetime.combine(eaten_date, dt.time(11, 52, 0)).isoformat(),
            "employee_id": employee_id,
            "meal_type": "중식",
            "corner_name": corner_name,
            "taste_score": taste,
            "comment": comment,
            "company_name": company_name,
            "menu_name": menu_name,
        }
    ]
    resp = client.post("/api/ingest/meal-log", json={"rows": rows}, headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_ingest_requires_token(client):
    resp = client.post("/api/ingest/weekly-menu", json={"rows": []})
    assert resp.status_code == 401


def test_ingest_weekly_menu_creates_menus_and_corners(client):
    result = _ingest_weekly_menu(client)
    assert result["inserted"] == 2
    assert result["new_menus"] == 2
    assert result["new_corners"] == 1


def test_ingest_meal_log_links_to_main_menu_snapshot(client, db_session):
    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E12345", "맛남", "맛있어요")

    from app.models.logs import MealLog

    log = db_session.query(MealLog).filter_by(employee_id="E12345").one()
    assert log.menu_id is not None  # 코너의 메인 메뉴(제육볶음)와 연결돼야 함

    from app.models.master import MenuMaster

    menu = db_session.query(MenuMaster).filter_by(menu_id=log.menu_id).one()
    assert menu.menu_name == "제육볶음"


def test_menu_food_vector_auto_tagged_by_rule_on_ingest(client, db_session):
    _ingest_weekly_menu(client)

    from app.models.master import MenuMaster

    menu = db_session.query(MenuMaster).filter_by(menu_name="제육볶음").one()
    assert menu.food_vector is not None  # "제육"(protein) + "볶음"(oily) 키워드에 걸림
    assert menu.food_vector_source.value == "규칙기반"


def test_menu_food_vector_stays_untagged_when_no_rule_matches(client, db_session):
    _ingest_meal_log(client, "E55555", "맛남", menu_name="모듬과일")

    from app.models.master import MenuMaster

    menu = db_session.query(MenuMaster).filter_by(menu_name="모듬과일").one()
    assert menu.food_vector is None
    assert menu.food_vector_source is None


def test_list_menu_food_vectors_endpoint(client):
    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E11111", "맛남")  # 코너의 메인 메뉴(제육볶음)와 자동 연결, 코너 "한식"
    _ingest_meal_log(client, "E55555", "맛남", menu_name="모듬과일", corner_name="분식")

    resp = client.get("/api/analysis/menus/food-vectors")
    assert resp.status_code == 200
    rows = resp.json()
    names = {row["menu_name"] for row in rows}
    assert "제육볶음" in names
    assert "모듬과일" in names
    assert "계란후라이" in names
    jeyuk = next(r for r in rows if r["menu_name"] == "제육볶음")
    assert jeyuk["corner_name"] == "한식"  # meal_log에서 실제 취식된 코너 기준
    moduem = next(r for r in rows if r["menu_name"] == "모듬과일")
    assert moduem["corner_name"] == "분식"  # 실제로 이 코너에서 취식됨
    gyeranhurai = next(r for r in rows if r["menu_name"] == "계란후라이")
    assert gyeranhurai["corner_name"] is None  # meal_log에 취식 기록이 없는 메뉴(부찬) — 코너 미배정

    resp_untagged = client.get("/api/analysis/menus/food-vectors", params={"untagged_only": True})
    untagged_names = {row["menu_name"] for row in resp_untagged.json()}
    assert untagged_names == {"모듬과일"}


def test_update_menu_food_vector_manual_override(client, db_session):
    _ingest_meal_log(client, "E55555", "맛남", menu_name="모듬과일")
    from app.models.master import MenuMaster

    menu = db_session.query(MenuMaster).filter_by(menu_name="모듬과일").one()

    vector = [0.1] * 10
    resp = client.put(f"/api/analysis/menus/{menu.menu_id}/food-vector", json={"vector": vector})
    assert resp.status_code == 200
    assert resp.json()["source"] == "관리자수동"

    db_session.refresh(menu)
    assert menu.food_vector_source.value == "관리자수동"
    assert list(menu.food_vector) == vector

    resp_bad_length = client.put(
        f"/api/analysis/menus/{menu.menu_id}/food-vector", json={"vector": [0.1] * 3}
    )
    assert resp_bad_length.status_code == 400

    resp_out_of_range = client.put(
        f"/api/analysis/menus/{menu.menu_id}/food-vector", json={"vector": [1.5] * 10}
    )
    assert resp_out_of_range.status_code == 400

    resp_missing = client.put("/api/analysis/menus/999999/food-vector", json={"vector": [0.1] * 10})
    assert resp_missing.status_code == 404


def test_tag_menus_with_llm_leaves_untagged_when_llm_unconfigured(client):
    _ingest_meal_log(client, "E55555", "맛남", menu_name="모듬과일")

    resp = client.post("/api/analysis/menus/tag-with-llm")
    assert resp.status_code == 200
    # 사내 LLM 미설정 환경에서는 모의 응답이 벡터 형식으로 파싱되지 않으므로 0건이어야 함
    assert resp.json()["tagged_menus"] == 0


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_menu_performance_recompute_and_read(client):
    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E1", "맛남")
    _ingest_meal_log(client, "E2", "맛남")
    _ingest_meal_log(client, "E3", "개선")

    resp = client.post(
        "/api/analysis/menu-performance/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["updated_menus"] >= 1

    resp = client.get(
        "/api/analysis/menu-performance",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    rows = resp.json()
    jeyuk = next(r for r in rows if r["menu_name"] == "제육볶음")
    assert jeyuk["evaluation_count"] == 3
    assert jeyuk["quadrant"] is not None
    assert jeyuk["corner_name"] == "한식"  # meal_log에서 실제 취식된 코너 기준


def test_menu_performance_recompute_excludes_take_out_placeholder_menus(client):
    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E1", "맛남")
    _ingest_meal_log(client, "E2", "맛남")
    _ingest_meal_log(client, "E3", "개선")
    # 테이크아웃 플레이스홀더 메뉴 — 4분면 집계 자체에서 빠져야 함(중앙값도 왜곡 안 함)
    _ingest_meal_log(client, "E4", "맛남", menu_name="선택형 Take out", corner_name="Take Out")
    _ingest_meal_log(client, "E5", "맛남", menu_name="(포장)메디쏠라", corner_name="Take Out")

    resp = client.post(
        "/api/analysis/menu-performance/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200

    resp = client.get(
        "/api/analysis/menu-performance",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    menu_names = {r["menu_name"] for r in resp.json()}
    assert "선택형 Take out" not in menu_names
    assert "(포장)메디쏠라" not in menu_names


def test_menu_highlights_detects_rising_menu_and_new_menu_reaction(client):
    _ingest_weekly_menu(client)  # 제육볶음/계란후라이, 한식, MONDAY

    prior_week = MONDAY - dt.timedelta(days=14)
    for i in range(3):
        _ingest_meal_log(client, f"P{i}", "개선", eaten_date=prior_week, menu_name="제육볶음", corner_name="한식")
    for i in range(3):
        _ingest_meal_log(client, f"R{i}", "맛남", eaten_date=MONDAY, menu_name="제육볶음", corner_name="한식")

    # 신메뉴 — 처음 등장하는 메뉴라 자동으로 is_new_menu=True로 찍힘
    resp = client.post(
        "/api/ingest/weekly-menu",
        json={
            "rows": [
                {
                    "plan_date": MONDAY.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "한식",
                    "menu_name": "신메뉴테스트",
                    "menu_role": "메인",
                    "source_row_raw": "신메뉴테스트",
                }
            ]
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    _ingest_meal_log(client, "N1", "맛남", eaten_date=MONDAY, menu_name="신메뉴테스트", corner_name="한식")

    resp = client.get("/api/dashboard/menu-highlights")
    assert resp.status_code == 200
    body = resp.json()

    rising_names = {r["menu_name"] for r in body["rising"]}
    falling_names = {r["menu_name"] for r in body["falling"]}
    assert "제육볶음" in rising_names
    assert "제육볶음" not in falling_names

    new_menu_names = {r["menu_name"] for r in body["new_menus"]}
    assert "신메뉴테스트" in new_menu_names
    new_menu_entry = next(r for r in body["new_menus"] if r["menu_name"] == "신메뉴테스트")
    assert new_menu_entry["evaluation_count"] == 1
    assert new_menu_entry["days_since_introduction"] == (dt.date.today() - MONDAY).days
    assert new_menu_entry["needs_attention"] is False  # 이미 평가가 있음


def test_menu_highlights_flags_new_menu_needing_attention_when_unevaluated(client):
    # 도입 후 오래됐는데(NEW_MENU_WINDOW_DAYS=30 이내지만 7일은 넘김) 평가가
    # 하나도 없으면 관심 유도가 필요하다는 신호(needs_attention)를 켠다.
    stale_date = dt.date.today() - dt.timedelta(days=10)
    resp = client.post(
        "/api/ingest/weekly-menu",
        json={
            "rows": [
                {
                    "plan_date": stale_date.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "한식",
                    "menu_name": "무관심신메뉴",
                    "menu_role": "메인",
                    "source_row_raw": "무관심신메뉴",
                }
            ]
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    resp = client.get("/api/dashboard/menu-highlights")
    assert resp.status_code == 200
    entry = next(r for r in resp.json()["new_menus"] if r["menu_name"] == "무관심신메뉴")
    assert entry["evaluation_count"] == 0
    assert entry["days_since_introduction"] == 10
    assert entry["needs_attention"] is True


def test_menu_highlights_excludes_side_dish_from_new_menus(client):
    # 신메뉴는 메인메뉴만 의미가 있다 — 같은 날 부찬으로 처음 등장한 메뉴는
    # is_new_menu=True로 찍혀도 하이라이트에 안 떠야 한다.
    resp = client.post(
        "/api/ingest/weekly-menu",
        json={
            "rows": [
                {
                    "plan_date": MONDAY.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "한식",
                    "menu_name": "신메뉴부찬",
                    "menu_role": "부찬",
                    "source_row_raw": "신메뉴부찬",
                }
            ]
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    resp = client.get("/api/dashboard/menu-highlights")
    assert resp.status_code == 200
    assert "신메뉴부찬" not in {r["menu_name"] for r in resp.json()["new_menus"]}

    # 관리자가 이 부찬을 수동으로 신메뉴 지정해도 하이라이트엔 안 떠야 한다.
    resp = client.put("/api/analysis/menus/new-menu-status", json={"menu_name": "신메뉴부찬", "is_new": True})
    assert resp.status_code == 200, resp.text
    resp = client.get("/api/dashboard/menu-highlights")
    assert "신메뉴부찬" not in {r["menu_name"] for r in resp.json()["new_menus"]}


def test_new_menu_status_manual_add_bypasses_auto_window(client):
    # meal-log만으로 생긴 메뉴는 weekly_menu_plan.is_new_menu가 전혀 안 찍히므로
    # 자동판정으로는 "신메뉴 반응"에 절대 안 뜬다 — 관리자가 직접 등록하면 떠야 함.
    _ingest_meal_log(client, "E1", "맛남", menu_name="관리자등록메뉴", corner_name="한식")

    resp = client.get("/api/dashboard/menu-highlights")
    assert "관리자등록메뉴" not in {r["menu_name"] for r in resp.json()["new_menus"]}

    resp = client.put(
        "/api/analysis/menus/new-menu-status", json={"menu_name": "관리자등록메뉴", "is_new": True}
    )
    assert resp.status_code == 200, resp.text

    resp = client.get("/api/dashboard/menu-highlights")
    entry = next(r for r in resp.json()["new_menus"] if r["menu_name"] == "관리자등록메뉴")
    assert entry["is_manual"] is True
    assert entry["days_since_introduction"] == 0
    assert entry["corner_name"] == "한식"


def test_new_menu_status_manual_remove_hides_auto_detected_menu(client):
    resp = client.post(
        "/api/ingest/weekly-menu",
        json={
            "rows": [
                {
                    "plan_date": MONDAY.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "한식",
                    "menu_name": "자동감지신메뉴",
                    "menu_role": "메인",
                    "source_row_raw": "자동감지신메뉴",
                }
            ]
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    resp = client.get("/api/dashboard/menu-highlights")
    assert "자동감지신메뉴" in {r["menu_name"] for r in resp.json()["new_menus"]}

    resp = client.put(
        "/api/analysis/menus/new-menu-status", json={"menu_name": "자동감지신메뉴", "is_new": False}
    )
    assert resp.status_code == 200

    resp = client.get("/api/dashboard/menu-highlights")
    assert "자동감지신메뉴" not in {r["menu_name"] for r in resp.json()["new_menus"]}


def test_weekly_menu_predicted_impact_returns_prediction_and_fallback_comment(client):
    _ingest_weekly_menu(client)  # 제육볶음(메인)/계란후라이(부찬), 한식, MONDAY
    for i in range(3):
        _ingest_meal_log(client, f"P{i}", "맛남", menu_name="제육볶음", corner_name="한식")

    resp = client.get(
        "/api/analysis/weekly-menu", params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()}
    )
    assert resp.status_code == 200
    slot = next(s for s in resp.json() if s["corner_name"] == "한식")
    main_plan_id = slot["main"]["plan_id"]
    side_plan_id = slot["sides"][0]["plan_id"]

    resp = client.get(f"/api/analysis/weekly-menu/{main_plan_id}/predicted-impact")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["main_menu"]["menu_name"] == "제육볶음"
    assert isinstance(body["prediction"]["predicted_headcount"], (int, float))
    assert isinstance(body["prediction"]["predicted_share"], (int, float))
    # 이 픽스처엔 과거 처리량 데이터가 없어 None(계산은 되지만 근거가 없다는 뜻)
    assert body["prediction"]["expected_wait_minutes"] is None
    assert "사내 LLM 미설정" in body["summary_comment"]  # 테스트 환경엔 사내 LLM 미설정

    # 메인이 아닌(부찬) plan_id로는 예측을 못 만든다
    resp = client.get(f"/api/analysis/weekly-menu/{side_plan_id}/predicted-impact")
    assert resp.status_code == 404

    resp = client.get("/api/analysis/weekly-menu/999999/predicted-impact")
    assert resp.status_code == 404


def test_weekly_menu_predicted_impact_summary_returns_numbers_without_llm_call(client):
    _ingest_weekly_menu(client)  # 제육볶음(메인)/계란후라이(부찬), 한식, MONDAY
    for i in range(3):
        _ingest_meal_log(client, f"P{i}", "맛남", menu_name="제육볶음", corner_name="한식")

    resp = client.get(
        "/api/analysis/weekly-menu/predicted-impact-summary",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1  # 이 기간엔 메인메뉴 슬롯이 하나(제육볶음)뿐
    row = rows[0]
    assert row["menu_name"] == "제육볶음"
    assert row["corner_name"] == "한식"
    assert row["plan_date"] == MONDAY.isoformat()
    assert row["meal_type"] == "중식"
    assert isinstance(row["prediction"]["predicted_headcount"], (int, float))
    assert isinstance(row["prediction"]["predicted_share"], (int, float))
    assert "expected_wait_minutes" in row["prediction"]
    assert "summary_comment" not in row  # LLM 호출 없이 숫자만


def test_predicted_impact_computes_expected_wait_minutes_from_peak_time_throughput(client):
    _ingest_weekly_menu(client)  # 제육볶음(메인)/계란후라이(부찬), 한식, MONDAY
    # 과거 두 날짜에 피크타임(11:40~12:20, _ingest_meal_log 기본 취식시각 11:52)
    # 취식 기록을 남겨 이 메뉴의 처리량 데이터를 만든다(min_day_count=2 충족).
    for offset_days in (14, 7):
        eaten_date = MONDAY - dt.timedelta(days=offset_days)
        for i in range(3):
            _ingest_meal_log(
                client, f"T{offset_days}_{i}", "맛남", eaten_date=eaten_date, menu_name="제육볶음", corner_name="한식"
            )
    # _baseline_headcount는 daily_corner_stats(집계 테이블)를 보므로, 예상
    # 식수가 0이 아니려면 그 두 날짜분을 집계해둬야 한다.
    resp = client.post(
        "/api/analysis/daily-stats/recompute",
        params={"period_start": (MONDAY - dt.timedelta(days=14)).isoformat(), "period_end": (MONDAY - dt.timedelta(days=7)).isoformat()},
    )
    assert resp.status_code == 200

    resp = client.get(
        "/api/analysis/weekly-menu", params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()}
    )
    main_plan_id = next(s for s in resp.json() if s["corner_name"] == "한식")["main"]["plan_id"]

    resp = client.get(f"/api/analysis/weekly-menu/{main_plan_id}/predicted-impact")
    assert resp.status_code == 200, resp.text
    # 이 픽스처는 과거 실적을 그대로 재현하는 시나리오(배수=1)라 피크 용량을
    # 안 넘어 0이 맞다 — 초과분(overflow>0)이 실제로 나오는 경우는
    # compute_expected_wait_minutes 순수함수 테스트(test_weekly_menu_prediction.py)로
    # 정확히 고정한다. 여기서는 배선(0 이상의 숫자가 나오는지)만 확인.
    expected_wait = resp.json()["prediction"]["expected_wait_minutes"]
    assert expected_wait is not None
    assert expected_wait >= 0


def test_new_menu_status_unknown_menu_name_404s(client):
    resp = client.put(
        "/api/analysis/menus/new-menu-status", json={"menu_name": "존재안함", "is_new": True}
    )
    assert resp.status_code == 404


def test_improvement_points_surfaces_congestion_satisfaction_voe(client):
    def eat(employee_id, corner_name, minute, taste="맛남", menu_name=None, comment=None, eaten_date=MONDAY):
        client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(eaten_date, dt.time(11, minute)).isoformat(),
                        "employee_id": employee_id,
                        "meal_type": "중식",
                        "corner_name": corner_name,
                        "menu_name": menu_name,
                        "taste_score": taste,
                        "comment": comment,
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )

    # 혼잡도: 한식은 식수는 많지만(20명) 피크타임(11:40~12:00) 안에는 2명만 —
    # 나머지는 피크 밖(13시)이라 서브속도가 낮게 잡힌다. 일품은 식수는 적지만
    # 전부 피크 안이라 서브속도가 높다.
    for i in range(2):
        eat(f"H{i}", "한식", 45, menu_name="비인기저조메뉴", taste="개선")
    for i in range(18):
        client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(MONDAY, dt.time(13, i % 60)).isoformat(),
                        "employee_id": f"H{i + 2}",
                        "meal_type": "중식",
                        "corner_name": "한식",
                        "menu_name": "비인기저조메뉴",
                        "taste_score": "개선",
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )
    for i in range(5):
        eat(f"I{i}", "일품", 46, menu_name="인기메뉴", taste="맛남")

    resp = client.post(
        "/api/analysis/daily-stats/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/api/analysis/menu-performance/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200

    # VOE: 이번 달엔 "위생" 코멘트가 늘고, 지난달엔 거의 없었음
    prior_month_date = (MONDAY.replace(day=1) - dt.timedelta(days=1))
    eat("V0", "한식", 50, comment="위생 상태가 별로였어요", eaten_date=prior_month_date)
    for i in range(4):
        eat(f"V{i + 1}", "한식", 51, comment="위생이 너무 안 좋아요", eaten_date=MONDAY)

    resp = client.get(
        "/api/dashboard/improvement-points",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    points = resp.json()
    axes = {p["axis"] for p in points}
    assert "congestion" in axes
    assert "satisfaction" in axes
    assert "voe" in axes

    congestion = next(p for p in points if p["axis"] == "congestion")
    assert "한식" in congestion["title"]
    satisfaction = next(p for p in points if p["axis"] == "satisfaction")
    assert "비인기저조메뉴" in satisfaction["title"]
    voe = next(p for p in points if p["axis"] == "voe")
    assert "위생" in voe["title"]
    # 테스트 환경엔 사내 LLM이 설정돼 있지 않으므로 폴백 요약(원문 예시)이 붙는다 —
    # 건수만이 아니라 실제 코멘트 내용도 함께 보여줘야 한다는 요청(2026-07)에 대응.
    assert "voe_summary" in voe
    assert "위생" in voe["voe_summary"]


def test_list_weekly_menu_groups_main_and_sides_with_deadline(client):
    _ingest_weekly_menu(client)  # 제육볶음(메인)/계란후라이(부찬), 한식, MONDAY

    resp = client.get(
        "/api/analysis/weekly-menu",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    slots = resp.json()
    assert len(slots) == 1
    slot = slots[0]
    assert slot["corner_name"] == "한식"
    assert slot["main"]["menu_name"] == "제육볶음"
    assert slot["main"]["role_source"] == "규칙기반"
    assert [s["menu_name"] for s in slot["sides"]] == ["계란후라이"]
    assert slot["feedback_deadline"] == (MONDAY - dt.timedelta(days=7)).isoformat()
    expected_past_deadline = dt.date.today() > (MONDAY - dt.timedelta(days=7))
    assert slot["is_past_deadline"] == expected_past_deadline


def test_update_weekly_menu_role_locks_role_source_to_manual(client, db_session):
    _ingest_weekly_menu(client)
    resp = client.get(
        "/api/analysis/weekly-menu",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    side_plan_id = resp.json()[0]["sides"][0]["plan_id"]

    # 부찬을 부찬인 채로(역할은 그대로) 관리자가 "확인 완료"로 저장하는 상황을
    # 가정 — role_source만 관리자수동으로 잠기는지 확인(메인 중복 생기는
    # 케이스는 group_weekly_menu_rows의 별도 관심사라 여기서 안 섞음).
    resp = client.put(f"/api/analysis/weekly-menu/{side_plan_id}/role", json={"menu_role": "부찬"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["menu_role"] == "부찬"
    assert body["role_source"] == "관리자수동"

    from app.models.logs import WeeklyMenuPlan

    plan = db_session.get(WeeklyMenuPlan, side_plan_id)
    db_session.refresh(plan)
    assert plan.role_source.value == "관리자수동"


def test_update_weekly_menu_role_to_main_demotes_previous_main(client, db_session):
    # 부찬을 메인으로 승격하면 기존 메인은 자동으로 부찬으로 내려가야 한다 —
    # 안 그러면 슬롯에 메인이 2개 남아 조회 화면과 시뮬레이션이 서로 다른
    # 메뉴를 "그 날의 메인"으로 볼 수 있다(실사용 중 발견).
    _ingest_weekly_menu(client)
    resp = client.get(
        "/api/analysis/weekly-menu",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    slot = resp.json()[0]
    old_main_plan_id = slot["main"]["plan_id"]
    side_plan_id = slot["sides"][0]["plan_id"]

    resp = client.put(f"/api/analysis/weekly-menu/{side_plan_id}/role", json={"menu_role": "메인"})
    assert resp.status_code == 200

    from app.models.logs import WeeklyMenuPlan

    old_main_plan = db_session.get(WeeklyMenuPlan, old_main_plan_id)
    db_session.refresh(old_main_plan)
    assert old_main_plan.menu_role.value == "부찬"
    assert old_main_plan.role_source.value == "관리자수동"

    # 조회 화면과 실제 DB 상태가 일치하는지 — 메인이 정확히 하나만 남아야 함
    resp = client.get(
        "/api/analysis/weekly-menu",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    slot = resp.json()[0]
    assert slot["main"]["plan_id"] == side_plan_id
    assert [s["plan_id"] for s in slot["sides"]] == [old_main_plan_id]


def test_update_weekly_menu_role_unknown_plan_returns_404(client):
    resp = client.put("/api/analysis/weekly-menu/999999/role", json={"menu_role": "메인"})
    assert resp.status_code == 404


def test_weekly_menu_feedback_create_and_list(client, db_session):
    _ingest_weekly_menu(client)
    from app.models.master import CornerMaster

    corner = db_session.query(CornerMaster).filter_by(corner_name="한식").one()

    resp = client.post(
        "/api/analysis/weekly-menu/feedback",
        json={"plan_date": MONDAY.isoformat(), "corner_id": corner.corner_id, "comment": "이 부찬 조합 별로예요"},
    )
    assert resp.status_code == 200
    assert resp.json()["comment"] == "이 부찬 조합 별로예요"

    resp = client.get(
        "/api/analysis/weekly-menu/feedback",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["corner_name"] == "한식"
    assert items[0]["comment"] == "이 부찬 조합 별로예요"


def test_weekly_menu_feedback_unknown_corner_returns_404(client):
    resp = client.post(
        "/api/analysis/weekly-menu/feedback",
        json={"plan_date": MONDAY.isoformat(), "corner_id": 999999, "comment": "테스트"},
    )
    assert resp.status_code == 404


def test_menu_side_combinations_compares_satisfaction_by_combo(client, db_session):
    week1 = MONDAY
    week2 = MONDAY + dt.timedelta(days=7)

    def ingest_slot(plan_date, side_name):
        resp = client.post(
            "/api/ingest/weekly-menu",
            json={
                "rows": [
                    {
                        "plan_date": plan_date.isoformat(),
                        "meal_type": "중식",
                        "corner_name": "한식",
                        "menu_name": "제육볶음",
                        "menu_role": "메인",
                        "source_row_raw": f"제육볶음\n{side_name}",
                    },
                    {
                        "plan_date": plan_date.isoformat(),
                        "meal_type": "중식",
                        "corner_name": "한식",
                        "menu_name": side_name,
                        "menu_role": "부찬",
                        "source_row_raw": f"제육볶음\n{side_name}",
                    },
                ]
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200

    ingest_slot(week1, "계란찜")
    ingest_slot(week2, "김치")

    for i in range(3):
        _ingest_meal_log(client, f"W1_{i}", "맛남", eaten_date=week1, menu_name="제육볶음", corner_name="한식")
    for i in range(3):
        _ingest_meal_log(client, f"W2_{i}", "개선", eaten_date=week2, menu_name="제육볶음", corner_name="한식")

    _set_food_vector(db_session, "제육볶음", [0.5] * 10)
    _set_food_vector(db_session, "계란찜", [0.1] * 10)
    _set_food_vector(db_session, "김치", [0.9] * 10)

    resp = client.get(
        "/api/analysis/menu-combinations/제육볶음",
        params={"period_start": week1.isoformat(), "period_end": week2.isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["menu_name"] == "제육볶음"
    combos = body["combos"]
    assert len(combos) == 2
    # 맛남(5점)이 개선(1점)보다 만족도가 높으므로 계란찜 조합이 먼저 나와야 함
    assert combos[0]["sides"] == ["계란찜"]
    assert combos[0]["avg_satisfaction"] == 5.0
    assert combos[0]["day_count"] == 1
    assert combos[1]["sides"] == ["김치"]
    assert combos[1]["avg_satisfaction"] == 1.0
    assert combos[0]["nutrition_profile"]["매운맛"] == 0.3  # (0.5+0.1)/2


def test_menu_side_combinations_unknown_menu_returns_404(client):
    resp = client.get(
        "/api/analysis/menu-combinations/존재하지않는메뉴",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 404


def test_reclassify_weekly_menu_roles_endpoint_no_op_when_llm_unconfigured(client):
    _ingest_weekly_menu(client)

    resp = client.post(
        "/api/analysis/weekly-menu/reclassify-roles-with-llm",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    # 사내 LLM 미설정 환경에서는 모의 응답이 "메인: OO" 형식으로 파싱되지 않으므로 0건
    assert resp.json()["reclassified_slots"] == 0


def test_dashboard_weekly_summary_classifies_days(client):
    resp = client.get(
        "/api/dashboard/weekly-summary",
        params={"start_date": MONDAY.isoformat(), "end_date": (MONDAY + dt.timedelta(days=6)).isoformat()},
    )
    assert resp.status_code == 200
    days = resp.json()
    assert len(days) == 7
    saturday = next(d for d in days if d["date"] == (MONDAY + dt.timedelta(days=5)).isoformat())
    assert saturday["classification"] == "주말+공휴일"


def test_corner_analysis_requires_daily_stats(client, db_session):
    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E1", "맛남")

    from app.services.aggregation import aggregate_daily_stats

    aggregate_daily_stats(db_session, MONDAY)

    resp = client.get(
        "/api/analysis/corners",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    rows = resp.json()
    hansik = next(r for r in rows if r["corner_name"] == "한식")
    assert hansik["headcount_total"] == 1


def test_corner_analysis_merges_take_out_aliases_and_excludes_on_request(client, db_session):
    from app.services.aggregation import aggregate_daily_stats

    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E1", "맛남", corner_name="Take Out R")
    _ingest_meal_log(client, "E2", "맛남", corner_name="Take Out M")
    _ingest_meal_log(client, "E3", "맛남", corner_name="Take Out L")
    aggregate_daily_stats(db_session, MONDAY)

    resp = client.get(
        "/api/analysis/corners",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    rows = resp.json()
    take_out_rows = [r for r in rows if r["corner_name"] == "Take Out"]
    assert len(take_out_rows) == 1  # R/M/L 세 이름이 하나로 합쳐짐
    assert take_out_rows[0]["headcount_total"] == 3
    assert not any(r["corner_name"] in ("Take Out R", "Take Out M", "Take Out L") for r in rows)

    resp = client.get(
        "/api/analysis/corners",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat(), "exclude_take_out": True},
    )
    rows = resp.json()
    assert not any(r["corner_name"] == "Take Out" for r in rows)


def test_corner_analysis_sorts_green_meat_last_regardless_of_headcount(client, db_session):
    from app.services.aggregation import aggregate_daily_stats

    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E1", "맛남", corner_name="한식")
    for i in range(5):
        _ingest_meal_log(client, f"G{i}", "맛남", corner_name="그린미트")
    aggregate_daily_stats(db_session, MONDAY)

    resp = client.get(
        "/api/analysis/corners",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    rows = resp.json()
    # 그린미트가 식수는 제일 많아도(5건 vs 1건) 항상 마지막이어야 한다
    assert rows[-1]["corner_name"] == "그린미트"
    assert rows[-1]["headcount_total"] == 5


def test_corner_analysis_trend_groups_by_period_and_corner(client, db_session):
    from app.services.aggregation import aggregate_daily_stats

    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E1", "맛남", eaten_date=MONDAY)
    _ingest_meal_log(client, "E2", "맛남", eaten_date=MONDAY + dt.timedelta(days=7))
    aggregate_daily_stats(db_session, MONDAY)
    aggregate_daily_stats(db_session, MONDAY + dt.timedelta(days=7))

    resp = client.get(
        "/api/analysis/corners/trend",
        params={
            "period_start": MONDAY.isoformat(),
            "period_end": (MONDAY + dt.timedelta(days=7)).isoformat(),
            "granularity": "weekly",
        },
    )
    assert resp.status_code == 200
    rows = resp.json()
    hansik_rows = [r for r in rows if r["corner_name"] == "한식"]
    assert len(hansik_rows) == 2  # 서로 다른 주 2개
    assert {r["headcount"] for r in hansik_rows} == {1, 1}


def test_daily_stats_recompute_backfills_range_for_corner_and_home_views(client):
    # 과거 기간(예: 6개월치)을 한꺼번에 적재했을 때, 매일 새벽 스케줄러가 "어제"
    # 하루치만 계산하는 것과 달리 이 엔드포인트는 기간 전체를 한 번에 채워야 한다.
    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E1", "맛남", eaten_date=MONDAY)
    _ingest_meal_log(client, "E2", "맛남", eaten_date=MONDAY + dt.timedelta(days=1))

    resp = client.post(
        "/api/analysis/daily-stats/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": (MONDAY + dt.timedelta(days=1)).isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["days_processed"] == 2

    corners_resp = client.get(
        "/api/analysis/corners",
        params={"period_start": MONDAY.isoformat(), "period_end": (MONDAY + dt.timedelta(days=1)).isoformat()},
    )
    hansik = next(r for r in corners_resp.json() if r["corner_name"] == "한식")
    assert hansik["headcount_total"] == 2

    divisions_resp = client.get(
        "/api/analysis/divisions",
        params={
            "period_start": MONDAY.isoformat(),
            "period_end": (MONDAY + dt.timedelta(days=1)).isoformat(),
            "granularity": "daily",
        },
    )
    assert sum(r["headcount"] for r in divisions_resp.json()) == 2


def test_daily_stats_recompute_rejects_inverted_range(client):
    resp = client.post(
        "/api/analysis/daily-stats/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": (MONDAY - dt.timedelta(days=1)).isoformat()},
    )
    assert resp.status_code == 400


def test_chat_stream_falls_back_to_mock_when_llm_unconfigured(client):
    resp = client.post(
        "/api/chat/stream", json={"messages": [{"role": "user", "content": "이번주 만족도 어때?"}]}
    )
    assert resp.status_code == 200
    # 모의 응답은 단어 단위 SSE 청크로 쪼개져 오므로 한 단어로 확인한다.
    assert "미설정" in resp.text
    assert "data: [DONE]" in resp.text


def test_weekly_summary_export_returns_xlsx(client):
    resp = client.get(
        "/api/dashboard/weekly-summary/export",
        params={"start_date": MONDAY.isoformat(), "end_date": (MONDAY + dt.timedelta(days=6)).isoformat()},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert resp.content[:2] == b"PK"  # xlsx는 zip 컨테이너이므로 PK 매직 바이트로 시작


def test_meal_log_export_returns_xlsx_for_selected_period(client, db_session):
    _ingest_weekly_menu(client)
    _ingest_meal_log(client, "E11111", "맛남", "맛있어요", company_name="삼성전자")
    _ingest_meal_log(client, "E22222", "보통", None, company_name="삼성SDI")
    # 기간 밖 데이터는 제외돼야 함
    _ingest_meal_log(client, "E33333", "개선", None, eaten_date=MONDAY + dt.timedelta(days=10))

    resp = client.get(
        "/api/dashboard/meal-log/export",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert resp.content[:2] == b"PK"

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(resp.content))
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0] == ("취식일시", "사번", "구분", "회사명", "식사구분", "코너", "메뉴", "맛평가", "의견")
    assert len(rows) == 3  # header + 2 rows (기간 밖 1건 제외)
    employee_ids = {row[1] for row in rows[1:]}
    assert employee_ids == {"E11111", "E22222"}


def test_simulation_what_if_returns_all_corners(client):
    _ingest_weekly_menu(client)
    resp = client.post(
        "/api/simulation/what-if",
        json={"target_date": MONDAY.isoformat(), "meal_type": "중식", "weather": "비"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] == "평일"
    assert any(c["corner_name"] == "한식" for c in body["corners"])


def test_congestion_forecast_adjusts_for_planned_menu_popularity(client, db_session):
    def eat(employee_id, corner_name, menu_name):
        r = client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(MONDAY, dt.time(11, 50)).isoformat(),
                        "employee_id": employee_id,
                        "meal_type": "중식",
                        "corner_name": corner_name,
                        "menu_name": menu_name,
                        "taste_score": "맛남",
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200

    # 한식: 인기메뉴A(8명) vs 비인기메뉴B(2명), 일품: 메뉴C(10명) — 전체 20명
    # share(A)=8/20=0.4, share(B)=2/20=0.1, 한식 평균share=(0.4+0.1)/2=0.25
    # → A가 계획되면 배수 0.4/0.25=1.6
    for i in range(8):
        eat(f"A{i}", "한식", "인기메뉴A")
    for i in range(2):
        eat(f"B{i}", "한식", "비인기메뉴B")
    for i in range(10):
        eat(f"C{i}", "일품", "메뉴C")

    resp = client.post(
        "/api/analysis/daily-stats/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/analysis/menu-performance/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200

    from app.models.master import MenuMaster

    menu_a = db_session.query(MenuMaster).filter_by(menu_name="인기메뉴A").one()

    # 미래 평일(다음 주 화요일)에 인기메뉴A가 한식 코너 메인으로 계획됨
    future_date = MONDAY + dt.timedelta(days=8)
    resp = client.post(
        "/api/ingest/weekly-menu",
        json={
            "rows": [
                {
                    "plan_date": future_date.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "한식",
                    "menu_name": "인기메뉴A",
                    "menu_role": "메인",
                    "source_row_raw": "인기메뉴A",
                }
            ]
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    resp = client.get(
        "/api/simulation/congestion-forecast",
        params={"target_date": future_date.isoformat(), "meal_type": "중식"},
    )
    assert resp.status_code == 200
    hansik = next(c for c in resp.json()["corners"] if c["corner_name"] == "한식")
    assert hansik["planned_menu_id"] == menu_a.menu_id
    assert hansik["menu_popularity_multiplier"] == 1.6
    # 코너 baseline(A+B 합계 10명) * 1.6배 = 16.0
    assert hansik["predicted_headcount"] == 16.0
    # 실측 meal_log가 전부 피크타임(11:50, 11:40~12:20) 안에서만 찍혀
    # peak_share_ratio=1.0 — 예상 피크 식수는 예상 식수와 같다("최고 혼잡
    # 예상 코너" 카드용 신규 필드, 2026-07).
    assert hansik["expected_peak_headcount"] == 16.0

    ilpum = next(c for c in resp.json()["corners"] if c["corner_name"] == "일품")
    assert ilpum["planned_menu_id"] is None
    assert ilpum["menu_popularity_multiplier"] is None
    assert ilpum["expected_peak_headcount"] == ilpum["predicted_headcount"]


def test_what_if_uses_quadrant_multiplier_for_planned_menu_with_performance_data(client, db_session):
    def eat(employee_id, corner_name, menu_name):
        r = client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(MONDAY, dt.time(11, 50)).isoformat(),
                        "employee_id": employee_id,
                        "meal_type": "중식",
                        "corner_name": corner_name,
                        "menu_name": menu_name,
                        "taste_score": "맛남",
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200

    # 수요 median=10, 평가건수 10 미만이면 표본부족으로 빠지므로 A=12(고수요,
    # 평가 충분)가 "인기메뉴"(POPULAR, 배수 1.20)로 분류되게 구성.
    for i in range(12):
        eat(f"A{i}", "한식", "인기메뉴A")
    for i in range(2):
        eat(f"B{i}", "한식", "비인기메뉴B")
    for i in range(10):
        eat(f"C{i}", "일품", "메뉴C")

    resp = client.post(
        "/api/analysis/daily-stats/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    resp = client.post(
        "/api/analysis/menu-performance/recompute",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200

    from app.models.master import CornerMaster, MenuMaster

    menu_a = db_session.query(MenuMaster).filter_by(menu_name="인기메뉴A").one()
    hansik_corner = db_session.query(CornerMaster).filter_by(corner_name="한식").one()

    # 확인: A가 실제로 인기메뉴(POPULAR)로 분류됐는지
    resp = client.get(
        "/api/analysis/menu-performance",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    a_row = next(r for r in resp.json() if r["menu_name"] == "인기메뉴A")
    assert a_row["quadrant"] == "인기메뉴"

    future_date = MONDAY + dt.timedelta(days=8)
    resp = client.post(
        "/api/simulation/what-if",
        json={
            "target_date": future_date.isoformat(),
            "meal_type": "중식",
            "new_menu_corner_id": hansik_corner.corner_id,
            "planned_menu_id": menu_a.menu_id,
        },
    )
    assert resp.status_code == 200
    hansik = next(c for c in resp.json()["corners"] if c["corner_name"] == "한식")
    # baseline(A+B 합계 14명) * 1.20(인기메뉴 배수, 기본 1.15보다 큼) = 16.8
    assert hansik["baseline_headcount"] == 14.0
    assert hansik["predicted_headcount"] == 16.8


def test_meal_log_ingest_classifies_division_from_company_name(client, db_session):
    _ingest_meal_log(client, "E1001", "맛남", company_name="삼성전자")
    _ingest_meal_log(client, "E1002", "맛남", company_name="삼성SDI")
    _ingest_meal_log(client, "E1003", "맛남", company_name="지리산")
    _ingest_meal_log(client, "E1004", "맛남")  # company_name 없음(과거 방식 호환)

    from app.models.master import EmployeeMaster

    employees = {
        e.employee_id: e for e in db_session.query(EmployeeMaster).filter(
            EmployeeMaster.employee_id.in_(["E1001", "E1002", "E1003", "E1004"])
        )
    }
    assert employees["E1001"].division.value == "본사"
    assert employees["E1001"].company_name == "삼성전자"
    assert employees["E1002"].division.value == "계열사"
    assert employees["E1002"].company_name == "삼성SDI"
    assert employees["E1003"].division.value == "기타"
    assert employees["E1004"].division.value == "기타"
    assert employees["E1004"].company_name is None


def test_division_analysis_daily_breakdown(client, db_session):
    _ingest_meal_log(client, "E3001", "맛남", company_name="삼성전자")
    _ingest_meal_log(client, "E3002", "맛남", company_name="삼성SDI")
    _ingest_meal_log(client, "E3003", "맛남", company_name="지리산")

    from app.services.aggregation import aggregate_daily_stats

    aggregate_daily_stats(db_session, MONDAY)

    resp = client.get(
        "/api/analysis/divisions",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    by_division = {r["division"]: r["headcount"] for r in resp.json()}
    assert by_division == {"본사": 1, "계열사": 1, "기타": 1}


def test_division_analysis_monthly_granularity_combines_days(client, db_session):
    from app.services.aggregation import aggregate_daily_stats

    day1 = MONDAY
    day2 = MONDAY + dt.timedelta(days=1)
    _ingest_meal_log(client, "E4001", "맛남", company_name="삼성전자", eaten_date=day1)
    _ingest_meal_log(client, "E4002", "맛남", company_name="삼성전자", eaten_date=day2)
    aggregate_daily_stats(db_session, day1)
    aggregate_daily_stats(db_session, day2)

    resp = client.get(
        "/api/analysis/divisions",
        params={"period_start": day1.isoformat(), "period_end": day2.isoformat(), "granularity": "monthly"},
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1  # 같은 달 두 날짜가 한 버킷으로 합쳐져야 함
    assert rows[0]["period"] == day1.strftime("%Y-%m")
    assert rows[0]["headcount"] == 2


def test_division_analysis_classification_filter(client, db_session):
    from app.services.aggregation import aggregate_daily_stats

    saturday = MONDAY + dt.timedelta(days=5)
    _ingest_meal_log(client, "E5001", "맛남", company_name="삼성전자", eaten_date=MONDAY)
    _ingest_meal_log(client, "E5002", "맛남", company_name="삼성전자", eaten_date=saturday)
    aggregate_daily_stats(db_session, MONDAY)
    aggregate_daily_stats(db_session, saturday)

    resp = client.get(
        "/api/analysis/divisions",
        params={
            "period_start": MONDAY.isoformat(),
            "period_end": saturday.isoformat(),
            "classification": "주말+공휴일",
        },
    )
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["period"] == saturday.isoformat()


def _set_food_vector(db_session, menu_name: str, vector: list[float]):
    from app.models.master import MenuMaster

    menu = db_session.query(MenuMaster).filter_by(menu_name=menu_name).one()
    menu.food_vector = vector
    db_session.commit()


def test_taste_clusters_recompute_and_list(client, db_session):
    # 매운맛 그룹(spicy 높음) 4명, 순한맛 그룹(protein 높음) 4명 — 명확히 갈리게 구성
    for i in range(4):
        _ingest_meal_log(client, f"S{i}", "맛남", company_name=None)
        r = client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(MONDAY, dt.time(12, i)).isoformat(),
                        "employee_id": f"S{i}",
                        "meal_type": "중식",
                        "corner_name": "한식",
                        "menu_name": "매운메뉴",
                        "taste_score": "맛남",
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
    for i in range(4):
        client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(MONDAY, dt.time(12, 30 + i)).isoformat(),
                        "employee_id": f"P{i}",
                        "meal_type": "중식",
                        "corner_name": "그린미트",
                        "menu_name": "고단백메뉴",
                        "taste_score": "맛남",
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )

    _set_food_vector(db_session, "매운메뉴", [0.9, 0.1, 0.1, 0.1, 0.1, 0.2, 0.1, 0.1, 0.1, 0.1])
    _set_food_vector(db_session, "고단백메뉴", [0.1, 0.1, 0.1, 0.1, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1])

    resp = client.post("/api/analysis/users/taste-profile/recompute")
    assert resp.status_code == 200
    assert resp.json()["updated_employees"] == 8

    # 표본 부족(8명인데 k=10 요구 -> 최소 20명 필요)이면 400
    resp = client.post("/api/analysis/users/taste-clusters/recompute", params={"k": 10})
    assert resp.status_code == 400

    resp = client.post("/api/analysis/users/taste-clusters/recompute", params={"k": 2})
    assert resp.status_code == 200
    assert resp.json()["clusters_created"] == 2

    resp = client.get("/api/analysis/users/taste-clusters")
    assert resp.status_code == 200
    clusters = resp.json()
    assert len(clusters) == 2
    assert {c["size"] for c in clusters} == {4, 4}
    labels = {c["label"] for c in clusters}
    assert any("매운맛" in label for label in labels)
    assert any("단백질" in label for label in labels)

    # 개별 사번 조회에도 소속 군집 라벨이 붙는지 확인
    resp = client.get("/api/analysis/users/S0/taste-profile")
    assert resp.status_code == 200
    assert resp.json()["cluster_label"] is not None


def test_taste_clusters_exclude_take_out_from_dominant_corner_and_top_menus(client, db_session):
    # 사번당 Take Out 방문(2회)이 한식 방문(1회)보다 많게 구성 — 제외 규칙이 없으면
    # dominant_corner/top_menus가 "Take Out"/"선택형 Take out"으로 잘못 나온다.
    def eat(employee_id, corner_name, menu_name, minute):
        r = client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(MONDAY, dt.time(11, minute)).isoformat(),
                        "employee_id": employee_id,
                        "meal_type": "중식",
                        "corner_name": corner_name,
                        "menu_name": menu_name,
                        "taste_score": "맛남",
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200

    for i in range(4):
        eat(f"T{i}", "한식", "김치찌개", i)
        eat(f"T{i}", "Take Out", "선택형 Take out", 10 + i)
        eat(f"T{i}", "Take Out", "선택형 Take out", 20 + i)

    _set_food_vector(db_session, "김치찌개", [0.5] * 10)

    resp = client.post("/api/analysis/users/taste-profile/recompute")
    assert resp.status_code == 200
    assert resp.json()["updated_employees"] == 4

    resp = client.post("/api/analysis/users/taste-clusters/recompute", params={"k": 1})
    assert resp.status_code == 200
    assert resp.json()["clusters_created"] == 1

    resp = client.get("/api/analysis/users/taste-clusters")
    cluster = resp.json()[0]
    assert cluster["dominant_corner"] == "한식"
    assert "선택형 Take out" not in cluster["top_menus"]
    assert cluster["top_menus"] == ["김치찌개"]


def test_menu_affinity_finds_co_occurring_menu(client):
    # 떡볶이 먹는 3명 중 2명이 짜장면도 먹음
    def eat(employee_id, menu_name, minute):
        client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(MONDAY, dt.time(11, minute)).isoformat(),
                        "employee_id": employee_id,
                        "meal_type": "중식",
                        "corner_name": "분식",
                        "menu_name": menu_name,
                        "taste_score": "맛남",
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )

    for emp in ["A1", "A2", "A3"]:
        eat(emp, "떡볶이", 0)
    for emp in ["A1", "A2"]:
        eat(emp, "짜장면", 10)
    for emp in ["B1", "B2", "B3"]:
        eat(emp, "돈까스", 20)

    resp = client.get(
        "/api/analysis/menu-affinity/떡볶이",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat(), "min_co_count": 1},
    )
    assert resp.status_code == 200
    rows = resp.json()
    jjajang = next(r for r in rows if r["menu_name"] == "짜장면")
    assert jjajang["co_count"] == 2
    assert jjajang["lift"] > 1


def test_menu_affinity_unknown_menu_returns_404(client):
    resp = client.get(
        "/api/analysis/menu-affinity/존재하지않는메뉴",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 404


def test_top_menu_pairs_ignores_corner_and_covers_whole_population(client):
    # 코너가 서로 다른(한식/양식) 두 사람이 같은 메뉴 쌍(떡볶이+짜장면)을 먹어도
    # 코너 구분 없이 하나의 쌍으로 잡혀야 한다.
    def eat(employee_id, corner_name, menu_name, minute):
        client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(MONDAY, dt.time(11, minute)).isoformat(),
                        "employee_id": employee_id,
                        "meal_type": "중식",
                        "corner_name": corner_name,
                        "menu_name": menu_name,
                        "taste_score": "맛남",
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )

    eat("A1", "한식", "떡볶이", 0)
    eat("A1", "양식", "짜장면", 10)
    eat("A2", "양식", "떡볶이", 20)
    eat("A2", "한식", "짜장면", 30)

    resp = client.get(
        "/api/analysis/menu-pairs/top",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat(), "min_co_count": 1},
    )
    assert resp.status_code == 200
    rows = resp.json()
    pair = next(r for r in rows if {r["menu_a"], r["menu_b"]} == {"떡볶이", "짜장면"})
    assert pair["co_count"] == 2


def test_top_menu_pairs_excludes_take_out_placeholder_menus(client):
    def eat(employee_id, corner_name, menu_name, minute):
        client.post(
            "/api/ingest/meal-log",
            json={
                "rows": [
                    {
                        "eaten_at": dt.datetime.combine(MONDAY, dt.time(11, minute)).isoformat(),
                        "employee_id": employee_id,
                        "meal_type": "중식",
                        "corner_name": corner_name,
                        "menu_name": menu_name,
                        "taste_score": "맛남",
                    }
                ]
            },
            headers=AUTH_HEADERS,
        )

    eat("A1", "한식", "떡볶이", 0)
    eat("A1", "Take Out", "선택형 Take out", 10)
    eat("A2", "한식", "떡볶이", 20)
    eat("A2", "Take Out", "선택형 Take out", 30)

    resp = client.get(
        "/api/analysis/menu-pairs/top",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat(), "min_co_count": 1},
    )
    assert resp.status_code == 200
    rows = resp.json()
    menu_names = {name for r in rows for name in (r["menu_a"], r["menu_b"])}
    assert "선택형 Take out" not in menu_names


def test_corner_core_layer_menu_pairs_splits_core_and_non_core(client, db_session):
    # 코어층(E1~E3): 한식 코너를 4번씩 방문(전체 방문도 4번, share=1.0)하며 떡볶이/짜장면을 번갈아 먹음
    for emp in ["E1", "E2", "E3"]:
        for day_offset, menu in enumerate(["떡볶이", "짜장면", "떡볶이", "짜장면"]):
            _ingest_meal_log(
                client,
                emp,
                "맛남",
                eaten_date=MONDAY + dt.timedelta(days=day_offset),
                menu_name=menu,
                corner_name="한식",
            )

    # 비코어층(N1~N3): 한식은 1번만(방문횟수 기준 미달), 양식을 주로 방문하며 스테이크/파스타를 먹음
    for emp in ["N1", "N2", "N3"]:
        _ingest_meal_log(client, emp, "맛남", eaten_date=MONDAY, menu_name="김치찌개", corner_name="한식")
        for day_offset, menu in enumerate(["스테이크", "파스타", "스테이크", "파스타", "스테이크"]):
            _ingest_meal_log(
                client,
                emp,
                "맛남",
                eaten_date=MONDAY + dt.timedelta(days=day_offset + 1),
                menu_name=menu,
                corner_name="양식",
            )

    from app.models.master import CornerMaster

    corner = db_session.query(CornerMaster).filter_by(corner_name="한식").one()

    resp = client.get(
        f"/api/analysis/corners/{corner.corner_id}/core-layer-menu-pairs",
        params={
            "period_start": MONDAY.isoformat(),
            "period_end": (MONDAY + dt.timedelta(days=10)).isoformat(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["corner_name"] == "한식"
    assert body["core_layer"]["employee_count"] == 3
    assert body["non_core"]["employee_count"] == 3

    core_pairs = {frozenset((p["menu_a"], p["menu_b"])) for p in body["core_layer"]["top_pairs"]}
    assert frozenset({"떡볶이", "짜장면"}) in core_pairs

    non_core_pairs = {frozenset((p["menu_a"], p["menu_b"])) for p in body["non_core"]["top_pairs"]}
    assert frozenset({"스테이크", "파스타"}) in non_core_pairs


def test_corner_core_layer_menu_pairs_excludes_take_out_placeholder_menus(client, db_session):
    # 코너별 분석의 메뉴 쌍에서 "선택형 Take out" 같은 플레이스홀더 메뉴가
    # 계속 나오던 문제 — build_employee_menu_sets에서 걸러야 한다.
    for emp in ["E1", "E2", "E3"]:
        for day_offset, menu in enumerate(["떡볶이", "짜장면", "떡볶이", "짜장면"]):
            _ingest_meal_log(
                client,
                emp,
                "맛남",
                eaten_date=MONDAY + dt.timedelta(days=day_offset),
                menu_name=menu,
                corner_name="한식",
            )
        _ingest_meal_log(
            client, emp, "맛남", eaten_date=MONDAY, menu_name="선택형 Take out", corner_name="한식"
        )

    from app.models.master import CornerMaster

    corner = db_session.query(CornerMaster).filter_by(corner_name="한식").one()

    resp = client.get(
        f"/api/analysis/corners/{corner.corner_id}/core-layer-menu-pairs",
        params={
            "period_start": MONDAY.isoformat(),
            "period_end": (MONDAY + dt.timedelta(days=10)).isoformat(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    pair_menu_names = {
        name for pair in body["core_layer"]["top_pairs"] for name in (pair["menu_a"], pair["menu_b"])
    }
    assert "선택형 Take out" not in pair_menu_names


def test_corner_core_layer_menu_pairs_surfaces_cross_corner_pairs(client, db_session):
    # 코어층(한식)이 매번 떡볶이(한식)와 스테이크(양식)를 함께 먹는다 — 같은
    # 코너 조합이 워낙 흔해 top_pairs에는 안 잡혀도, 다른 코너 조합 전용
    # 목록(cross_corner_pairs)에는 이 쌍이 코너 태그와 함께 잡혀야 한다.
    for emp in ["E1", "E2", "E3"]:
        for day_offset in range(4):
            _ingest_meal_log(
                client,
                emp,
                "맛남",
                eaten_date=MONDAY + dt.timedelta(days=day_offset),
                menu_name="떡볶이",
                corner_name="한식",
            )
            _ingest_meal_log(
                client,
                emp,
                "맛남",
                eaten_date=MONDAY + dt.timedelta(days=day_offset),
                menu_name="스테이크",
                corner_name="양식",
            )

    from app.models.master import CornerMaster

    corner = db_session.query(CornerMaster).filter_by(corner_name="한식").one()

    resp = client.get(
        f"/api/analysis/corners/{corner.corner_id}/core-layer-menu-pairs",
        params={
            "period_start": MONDAY.isoformat(),
            "period_end": (MONDAY + dt.timedelta(days=10)).isoformat(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    cross_pairs = body["core_layer"]["cross_corner_pairs"]
    target = frozenset({"떡볶이", "스테이크"})
    entry = next(p for p in cross_pairs if frozenset((p["menu_a"], p["menu_b"])) == target)
    assert entry["corner_a"] != entry["corner_b"]
    assert {entry["corner_a"], entry["corner_b"]} == {"한식", "양식"}


def test_corner_core_layer_menu_pairs_includes_menu_controlled_preference(client, db_session):
    # 같은 날 같은 메인메뉴("공용메뉴")가 한식·일품 두 코너에서 동시 제공됨 —
    # 메뉴가 같으니 코너 선택은 순수 코너 선호를 반영한다고 본다(PRD, 2026-07).
    resp = client.post(
        "/api/ingest/weekly-menu",
        json={
            "rows": [
                {
                    "plan_date": MONDAY.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "한식",
                    "menu_name": "공용메뉴",
                    "menu_role": "메인",
                    "source_row_raw": "공용메뉴",
                },
                {
                    "plan_date": MONDAY.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "일품",
                    "menu_name": "공용메뉴",
                    "menu_role": "메인",
                    "source_row_raw": "공용메뉴",
                },
            ]
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    # 4명 중 3명은 한식에서, 1명은 일품에서 공용메뉴를 먹음
    for i in range(3):
        _ingest_meal_log(client, f"H{i}", "맛남", eaten_date=MONDAY, menu_name="공용메뉴", corner_name="한식")
    _ingest_meal_log(client, "I0", "맛남", eaten_date=MONDAY, menu_name="공용메뉴", corner_name="일품")

    from app.models.master import CornerMaster

    corner = db_session.query(CornerMaster).filter_by(corner_name="한식").one()

    resp = client.get(
        f"/api/analysis/corners/{corner.corner_id}/core-layer-menu-pairs",
        params={"period_start": MONDAY.isoformat(), "period_end": (MONDAY + dt.timedelta(days=1)).isoformat()},
    )
    assert resp.status_code == 200
    pref = resp.json()["menu_controlled_preference"]
    assert pref is not None
    assert pref["contested_occasions"] == 4
    assert pref["chosen_count"] == 3
    assert pref["preference_ratio"] == 0.75


def test_top_menu_pairs_includes_is_obvious_pair_flag(client):
    for i in range(3):
        _ingest_meal_log(client, f"E{i}", "맛남", eaten_date=MONDAY, menu_name="떡볶이", corner_name="분식")
        _ingest_meal_log(client, f"E{i}", "맛남", eaten_date=MONDAY, menu_name="순대", corner_name="분식")

    resp = client.get(
        "/api/analysis/menu-pairs/top",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat(), "min_co_count": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) > 0
    assert "is_obvious_pair" in body[0]
    # food_vector가 태깅 안 된 테스트 메뉴라 판단 불가(None)여도 필드 자체는 있어야 함
    assert body[0]["is_obvious_pair"] in (None, True, False)


def test_corner_core_layer_menu_pairs_unknown_corner_returns_404(client):
    resp = client.get(
        "/api/analysis/corners/999999/core-layer-menu-pairs",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 404


def test_corner_menu_throughput_sorts_slowest_menu_first(client, db_session):
    # 느린메뉴가 나온 날은 피크타임(11:40~12:00, _ingest_meal_log 기본 취식시각
    # 11:52는 이 구간 안)에 2명만 먹고, 빠른메뉴가 나온 날은 10명이 먹는다 —
    # 처리량(분당 서브)이 낮을수록(=느릴수록) 먼저 나와야 한다.
    for i in range(2):
        _ingest_meal_log(client, f"S{i}", "맛남", eaten_date=MONDAY, menu_name="느린메뉴", corner_name="한식")
    for i in range(2):
        _ingest_meal_log(
            client, f"S{i}b", "맛남", eaten_date=MONDAY + dt.timedelta(days=7), menu_name="느린메뉴", corner_name="한식"
        )
    for i in range(10):
        _ingest_meal_log(
            client, f"F{i}", "맛남", eaten_date=MONDAY + dt.timedelta(days=1), menu_name="빠른메뉴", corner_name="한식"
        )
    for i in range(10):
        _ingest_meal_log(
            client, f"F{i}b", "맛남", eaten_date=MONDAY + dt.timedelta(days=8), menu_name="빠른메뉴", corner_name="한식"
        )

    from app.models.master import CornerMaster

    corner = db_session.query(CornerMaster).filter_by(corner_name="한식").one()

    resp = client.get(
        f"/api/analysis/corners/{corner.corner_id}/menu-throughput",
        params={"period_start": MONDAY.isoformat(), "period_end": (MONDAY + dt.timedelta(days=8)).isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [m["menu_name"] for m in body["menus"]] == ["느린메뉴", "빠른메뉴"]
    assert body["menus"][0]["avg_throughput"] < body["menus"][1]["avg_throughput"]
    assert body["menus"][0]["day_count"] == 2
    assert body["overall_avg_throughput"] is not None


def test_corner_menu_throughput_unknown_corner_returns_404(client):
    resp = client.get(
        "/api/analysis/corners/999999/menu-throughput",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 404


def test_voe_by_category_groups_comments_into_fixed_categories(client):
    _ingest_meal_log(client, "E1", "맛남", comment="정말 맛있어요")
    _ingest_meal_log(client, "E2", "개선", comment="국이 너무 싱거워요")
    _ingest_meal_log(client, "E3", "개선", comment="위생 상태가 별로였어요")
    _ingest_meal_log(client, "E4", "개선", comment="직원분이 불친절했어요")
    _ingest_meal_log(client, "E5", "보통", comment="그냥 평범했어요")  # 기타로 분류
    _ingest_meal_log(client, "E6", "맛남", comment=None)  # 코멘트 없음 — 집계 제외

    resp = client.get("/api/dashboard/voe-by-category", params={"period": f"{MONDAY.isoformat()[:7]}-01"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_comments"] == 5
    categories = {c["category"]: c for c in body["categories"]}
    assert [c["category"] for c in body["categories"]] == ["맛", "간", "위생", "서비스", "기타"]
    assert categories["맛"]["count"] == 1
    assert categories["간"]["count"] == 1
    assert categories["위생"]["count"] == 1
    assert categories["서비스"]["count"] == 1
    assert categories["기타"]["count"] == 1
    assert categories["기타"]["comments"][0]["comment"] == "그냥 평범했어요"


def test_voe_by_category_multi_label_comment_counted_in_both_categories(client):
    _ingest_meal_log(client, "E1", "개선", comment="맛없고 위생도 별로예요")

    resp = client.get("/api/dashboard/voe-by-category", params={"period": f"{MONDAY.isoformat()[:7]}-01"})
    body = resp.json()
    categories = {c["category"]: c for c in body["categories"]}

    assert body["total_comments"] == 1
    assert categories["맛"]["count"] == 1
    assert categories["위생"]["count"] == 1
    assert categories["간"]["count"] == 0


def test_voe_by_category_prefers_stored_llm_categories_over_rule_based(client, db_session):
    # "정말 좋아요"는 규칙 기반으로는 어느 카테고리에도 안 걸리지만(기타로 감),
    # voe_categories가 이미 채워져 있으면(LLM 배치 결과) 그걸 그대로 써야 한다.
    _ingest_meal_log(client, "E1", "맛남", comment="정말 좋아요")

    from app.models.logs import MealLog

    log = db_session.query(MealLog).filter_by(employee_id="E1").one()
    log.voe_categories = ["서비스"]
    db_session.commit()

    resp = client.get("/api/dashboard/voe-by-category", params={"period": f"{MONDAY.isoformat()[:7]}-01"})
    body = resp.json()
    categories = {c["category"]: c for c in body["categories"]}
    assert categories["서비스"]["count"] == 1
    assert categories["기타"]["count"] == 0


def test_voe_by_category_recompute_falls_back_to_rules_when_llm_unconfigured(client, db_session):
    _ingest_meal_log(client, "E1", "맛남", comment="정말 맛있어요")

    resp = client.post(
        "/api/dashboard/voe-by-category/recompute", params={"period": f"{MONDAY.isoformat()[:7]}-01"}
    )
    assert resp.status_code == 200
    assert resp.json()["classified_comments"] == 1

    from app.models.logs import MealLog

    log = db_session.query(MealLog).filter_by(employee_id="E1").one()
    assert log.voe_categories == ["맛"]


def test_voe_clusters_recompute_creates_clusters_from_comments(client, db_session):
    # 사내 LLM 미설정 환경이라 llm_client의 모의 임베딩/응답으로 배선만 검증한다
    # (voe_clustering.py의 실제 군집 품질은 사내 LLM 연동 후 별도 확인 필요).
    _ingest_meal_log(client, "E1", "맛남", comment="정말 맛있어요")
    _ingest_meal_log(client, "E2", "개선", comment="너무 짰어요")

    resp = client.post(
        "/api/dashboard/voe-clusters/recompute", params={"period": f"{MONDAY.isoformat()[:7]}-01"}
    )
    assert resp.status_code == 200
    assert resp.json()["clusters_created"] >= 1

    resp = client.get("/api/dashboard/voe-clusters", params={"period": f"{MONDAY.isoformat()[:7]}-01"})
    assert resp.status_code == 200
    clusters = resp.json()
    assert len(clusters) >= 1
    assert sum(c["comment_count"] for c in clusters) == 2


def test_average_menu_food_vector_uses_only_main_menus(client, db_session):
    _ingest_weekly_menu(client)  # 제육볶음(메인)/계란후라이(부찬), 한식, MONDAY

    from app.models.master import MenuMaster
    from app.services.food_vector import FOOD_VECTOR_DIM

    main = db_session.query(MenuMaster).filter_by(menu_name="제육볶음").one()
    side = db_session.query(MenuMaster).filter_by(menu_name="계란후라이").one()
    main.food_vector = [0.9] + [0.5] * (FOOD_VECTOR_DIM - 1)
    side.food_vector = [0.1] + [0.5] * (FOOD_VECTOR_DIM - 1)  # 부찬 — 평균에서 제외돼야 함
    db_session.commit()

    resp = client.get("/api/analysis/menus/food-vectors/average")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_size"] == 1
    assert body["average"][0] == pytest.approx(0.9, abs=1e-4)
    assert body["dimensions"] == list(body["labels_ko"].keys())
    assert body["bias_description"] is not None


def test_average_menu_food_vector_empty_when_no_tagged_main_menus(client):
    resp = client.get("/api/analysis/menus/food-vectors/average")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_size"] == 0
    assert body["bias_description"] is None


def test_menu_comments_returns_recent_comments_newest_first(client):
    _ingest_meal_log(client, "E1", "맛남", comment="맛있어요", eaten_date=MONDAY, menu_name="제육볶음")
    _ingest_meal_log(
        client, "E2", "개선", comment="좀 짰어요", eaten_date=MONDAY + dt.timedelta(days=1), menu_name="제육볶음"
    )
    _ingest_meal_log(client, "E3", "맛남", comment=None, eaten_date=MONDAY, menu_name="제육볶음")

    resp = client.get("/api/dashboard/menu-comments/제육볶음")
    assert resp.status_code == 200
    body = resp.json()
    assert [c["comment"] for c in body] == ["좀 짰어요", "맛있어요"]
    assert body[0]["taste_score"] == "개선"


def test_menu_comments_unknown_menu_returns_404(client):
    resp = client.get("/api/dashboard/menu-comments/없는메뉴")
    assert resp.status_code == 404


def test_corner_main_menu_by_date_returns_main_menu_only(client):
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
                    "source_row_raw": "제육볶음",
                },
                {
                    "plan_date": MONDAY.isoformat(),
                    "meal_type": "중식",
                    "corner_name": "한식",
                    "menu_name": "김치",
                    "menu_role": "부찬",
                    "source_row_raw": "김치",
                },
            ]
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    resp = client.get(
        "/api/analysis/corners/main-menu-by-date",
        params={"period_start": MONDAY.isoformat(), "period_end": MONDAY.isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["menu_name"] == "제육볶음"
    assert body[0]["plan_date"] == MONDAY.isoformat()
