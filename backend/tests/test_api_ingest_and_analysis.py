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
):
    rows = [
        {
            "eaten_at": dt.datetime.combine(eaten_date, dt.time(11, 52, 0)).isoformat(),
            "employee_id": employee_id,
            "meal_type": "중식",
            "corner_name": "한식",
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
