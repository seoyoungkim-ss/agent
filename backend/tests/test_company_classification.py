from app.models.enums import Division
from app.services.company_classification import classify_division


def test_headquarters():
    assert classify_division("삼성전자") == Division.HEADQUARTERS


def test_affiliates():
    assert classify_division("삼성SDI") == Division.AFFILIATE
    assert classify_division("삼성에스원") == Division.AFFILIATE
    assert classify_division("삼성SDS") == Division.AFFILIATE


def test_unknown_company_is_other():
    assert classify_division("지리산") == Division.OTHER
    assert classify_division("제일원") == Division.OTHER


def test_blank_or_none_is_other():
    assert classify_division(None) == Division.OTHER
    assert classify_division("") == Division.OTHER
    assert classify_division("   ") == Division.OTHER


def test_whitespace_tolerant():
    assert classify_division(" 삼성전자 ") == Division.HEADQUARTERS
