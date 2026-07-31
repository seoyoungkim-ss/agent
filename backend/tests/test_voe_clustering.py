import datetime as dt

import pytest

import app.api.dashboard as dashboard_module
from app.config import Settings
from app.models.enums import Division, MealType
from app.models.logs import MealLog
from app.models.master import CornerMaster, EmployeeMaster
from app.services.llm_client import InternalLLMClient
from app.services.voe_clustering import cluster_monthly_voe


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
async def test_cluster_monthly_voe_succeeds_with_mock_embeddings(db_session):
    _seed_comments(db_session, ["맛있어요", "위생이 별로예요", "친절해요"])
    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))

    clusters_created = await cluster_monthly_voe(db_session, dt.date(2026, 6, 1), client)

    assert clusters_created > 0


@pytest.mark.asyncio
async def test_cluster_monthly_voe_no_comments_returns_zero(db_session):
    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))
    assert await cluster_monthly_voe(db_session, dt.date(2026, 6, 1), client) == 0


@pytest.mark.asyncio
async def test_cluster_monthly_voe_raises_clear_error_on_embedding_count_mismatch(db_session, monkeypatch):
    _seed_comments(db_session, ["맛있어요", "별로예요"])
    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))

    async def bad_embed(texts):
        return [[0.1] * 8]  # 코멘트 2개인데 임베딩 1개만 반환 — 개수 불일치

    monkeypatch.setattr(client, "embed", bad_embed)

    with pytest.raises(ValueError, match="임베딩 개수"):
        await cluster_monthly_voe(db_session, dt.date(2026, 6, 1), client)


@pytest.mark.asyncio
async def test_cluster_monthly_voe_raises_clear_error_on_ragged_embedding_dims(db_session, monkeypatch):
    _seed_comments(db_session, ["맛있어요", "별로예요"])
    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))

    async def ragged_embed(texts):
        return [[0.1] * 8, [0.1] * 4]  # 두 번째 벡터만 차원이 다름

    monkeypatch.setattr(client, "embed", ragged_embed)

    with pytest.raises(ValueError, match="차원이 서로 다릅니다"):
        await cluster_monthly_voe(db_session, dt.date(2026, 6, 1), client)


@pytest.mark.asyncio
async def test_cluster_monthly_voe_falls_back_to_unclassified_when_summary_call_fails(db_session, monkeypatch):
    _seed_comments(db_session, ["맛있어요", "별로예요", "친절해요"])
    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))

    async def failing_chat_complete(messages):
        raise RuntimeError("사내 LLM 게이트웨이 타임아웃")

    monkeypatch.setattr(client, "chat_complete", failing_chat_complete)

    clusters_created = await cluster_monthly_voe(db_session, dt.date(2026, 6, 1), client)

    assert clusters_created > 0  # 라벨 요약이 실패해도 클러스터링 자체는 성공


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

    async def failing_embed(self, texts):
        raise RuntimeError("사내 LLM 게이트웨이 연결 실패")

    monkeypatch.setattr(dashboard_module.InternalLLMClient, "embed", failing_embed)

    response = client.post("/api/dashboard/voe-clusters/recompute", params={"period": "2026-06-01"})

    assert response.status_code == 502
    assert "사내 LLM" in response.json()["detail"]
