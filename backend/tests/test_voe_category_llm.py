import datetime as dt

import pytest

from app.config import Settings
from app.models.enums import Division, MealType
from app.models.logs import MealLog
from app.models.master import CornerMaster, EmployeeMaster
from app.services.llm_client import InternalLLMClient
from app.services.voe_category_llm import _parse_batch_response, classify_monthly_voe_via_llm


def test_parse_batch_response_extracts_categories_and_keywords():
    response = (
        "1. 카테고리: 맛,간 | 키워드: 짜다, 맛없다\n"
        "2. 카테고리: 기타 | 키워드: 없음\n"
        "3. 카테고리: 위생 | 키워드: 머리카락\n"
    )
    results = _parse_batch_response(response, 3)
    assert results[0] == (["맛", "간"], ["짜다", "맛없다"])
    assert results[1] == ([], [])  # 기타는 빈 카테고리로 남김 — 호출부가 기타로 대체
    assert results[2] == (["위생"], ["머리카락"])


def test_parse_batch_response_ignores_malformed_lines_and_pads_missing():
    response = "이상한 응답 형식\n1. 카테고리: 서비스 | 키워드: 불친절"
    results = _parse_batch_response(response, 3)
    assert results[0] == (["서비스"], ["불친절"])
    assert results[1] == ([], [])
    assert results[2] == ([], [])


def test_parse_batch_response_drops_unknown_category_names():
    response = "1. 카테고리: 맛,알수없음 | 키워드: 맛있다"
    results = _parse_batch_response(response, 1)
    assert results[0] == (["맛"], ["맛있다"])


@pytest.mark.asyncio
async def test_classify_monthly_voe_via_llm_falls_back_to_rules_when_unconfigured(db_session):
    corner = CornerMaster(corner_name="한식")
    employee = EmployeeMaster(employee_id="E1", division=Division.OTHER)
    db_session.add_all([corner, employee])
    db_session.flush()
    log = MealLog(
        eaten_at=dt.datetime(2026, 6, 25, 12, 0, 0),
        employee_id="E1",
        meal_type=MealType.LUNCH,
        corner_id=corner.corner_id,
        comment="정말 맛있어요",
    )
    db_session.add(log)
    db_session.commit()

    client = InternalLLMClient(Settings(internal_llm_base_url="", internal_llm_api_key=""))
    classified = await classify_monthly_voe_via_llm(db_session, dt.date(2026, 6, 1), client)

    assert classified == 1
    db_session.refresh(log)
    assert log.voe_categories == ["맛"]
    assert log.voe_keywords is None
