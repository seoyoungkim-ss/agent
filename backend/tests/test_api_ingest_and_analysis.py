import datetime as dt

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


def _ingest_meal_log(client, employee_id: str, taste: str, comment: str | None = None, company_name: str | None = None):
    rows = [
        {
            "eaten_at": dt.datetime.combine(MONDAY, dt.time(11, 52, 0)).isoformat(),
            "employee_id": employee_id,
            "meal_type": "중식",
            "corner_name": "한식",
            "taste_score": taste,
            "comment": comment,
            "company_name": company_name,
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
