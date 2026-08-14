import datetime as dt

import pytest

import app.api.dashboard as dashboard_module
from app.config import Settings
from app.models.enums import Division, MealType
from app.models.logs import MealLog
from app.models.master import CornerMaster, EmployeeMaster
from app.services.llm_client import InternalLLMClient
from app.services.voe_clustering import _parse_cluster_response, cluster_monthly_voe


def _seed_comments(db_session, comments: list[str]) -> None:
    corner = CornerMaster(corner_name="한식")
    employee = EmployeeMaster(employee_id="E1", division=Division.OTHER)
    db_session.add_all([corner, employee])
    db_session.flush()
    for i, comment in enumerate(comments):
        db_session.add(
            MealLog(
                eaten_at=dt.datetime(2026, 6, 10 + i, 12, 0, 0),
                employee_id="E1",
                meal_type=MealType.LUNCH,
                corner_id=corner.corner_id,
                comment=comment,
            )
        )
    db_session.commit()


@pytest.mark.asyncio
async def test_cluster_monthly_voe_succeeds_with_mock_chat_reply(db_session):
    _seed_comments(db_session, ["맛있어요", "위생이 별로예요", "친절해요"])
    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))

    clusters_created = await cluster_monthly_voe(db_session, dt.date(2026, 6, 1), client)

    assert clusters_created > 0


@pytest.mark.asyncio
async def test_cluster_monthly_voe_no_comments_returns_zero(db_session):
    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))
    assert await cluster_monthly_voe(db_session, dt.date(2026, 6, 1), client) == 0


@pytest.mark.asyncio
async def test_cluster_monthly_voe_groups_comments_via_chat_response(db_session, monkeypatch):
    _seed_comments(db_session, ["맛있어요", "위생이 별로예요", "친절해요", "짜요"])
    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))

    async def two_group_reply(messages):
        return (
            "라벨: 맛 관련\n"
            "키워드: 맛있음, 짬\n"
            "대표코멘트: 맛있어요\n"
            "번호: 1,4\n"
            "\n"
            "라벨: 서비스 관련\n"
            "키워드: 위생, 친절\n"
            "대표코멘트: 위생이 별로예요\n"
            "번호: 2,3"
        )

    monkeypatch.setattr(client, "chat_complete", two_group_reply)

    clusters_created = await cluster_monthly_voe(db_session, dt.date(2026, 6, 1), client)

    assert clusters_created == 2


@pytest.mark.asyncio
async def test_cluster_monthly_voe_raises_when_no_clusters_parsed(db_session, monkeypatch):
    _seed_comments(db_session, ["맛있어요", "별로예요"])
    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))

    async def unparseable_reply(messages):
        return "죄송하지만 그룹으로 나눌 수 없습니다."

    monkeypatch.setattr(client, "chat_complete", unparseable_reply)

    with pytest.raises(ValueError, match="파싱하지 못했습니다"):
        await cluster_monthly_voe(db_session, dt.date(2026, 6, 1), client)


def test_parse_cluster_response_ignores_out_of_range_numbers():
    sample = ["a", "b"]
    response = "라벨: 테스트\n키워드: k1\n대표코멘트: a\n번호: 1,2,99,abc"

    clusters = _parse_cluster_response(response, sample)

    assert len(clusters) == 1
    label, representative, comment_count, keywords = clusters[0]
    assert comment_count == 2  # 99와 abc는 범위 밖/숫자 아님이라 제외
    assert representative == "a"
    assert keywords == ["k1"]


def test_parse_cluster_response_skips_blocks_without_valid_numbers():
    sample = ["a", "b"]
    response = "라벨: 빈 그룹\n키워드: k1\n대표코멘트: a\n번호: 99,xyz"

    clusters = _parse_cluster_response(response, sample)

    assert clusters == []


def test_recompute_voe_clusters_endpoint_succeeds(client, db_session):
    corner = CornerMaster(corner_name="한식")
    employee = EmployeeMaster(employee_id="E1", division=Division.OTHER)
    db_session.add_all([corner, employee])
    db_session.flush()
    db_session.add(
        MealLog(
            eaten_at=dt.datetime(2026, 6, 10, 12, 0, 0),
            employee_id="E1",
            meal_type=MealType.LUNCH,
            corner_id=corner.corner_id,
            comment="맛있어요",
        )
    )
    db_session.commit()

    response = client.post("/api/dashboard/voe-clusters/recompute", params={"period": "2026-06-01"})

    assert response.status_code == 200
    assert response.json()["clusters_created"] > 0


def test_recompute_voe_clusters_endpoint_surfaces_upstream_failure_as_502(client, db_session, monkeypatch):
    corner = CornerMaster(corner_name="한식")
    employee = EmployeeMaster(employee_id="E1", division=Division.OTHER)
    db_session.add_all([corner, employee])
    db_session.flush()
    db_session.add(
        MealLog(
            eaten_at=dt.datetime(2026, 6, 10, 12, 0, 0),
            employee_id="E1",
            meal_type=MealType.LUNCH,
            corner_id=corner.corner_id,
            comment="맛있어요",
        )
    )
    db_session.commit()

    async def failing_chat_complete(self, messages):
        raise RuntimeError("사내 LLM 채팅 게이트웨이 연결 실패")

    monkeypatch.setattr(dashboard_module.InternalLLMClient, "chat_complete", failing_chat_complete)

    response = client.post("/api/dashboard/voe-clusters/recompute", params={"period": "2026-06-01"})

    assert response.status_code == 502
    assert "사내 LLM" in response.json()["detail"]
