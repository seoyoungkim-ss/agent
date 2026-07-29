import datetime as dt
import io

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
    _ingest_meal_log(client, "E55555", "맛남", menu_name="모듬과일")

    resp = client.get("/api/analysis/menus/food-vectors")
    assert resp.status_code == 200
    names = {row["menu_name"] for row in resp.json()}
    assert "제육볶음" in names
    assert "모듬과일" in names

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


def test_corner_core_layer_menu_pairs_unknown_corner_returns_404(client):
    resp = client.get(
        "/api/analysis/corners/999999/core-layer-menu-pairs",
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
