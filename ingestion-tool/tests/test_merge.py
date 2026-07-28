import datetime as dt

from models import MealType, ParsedMealTransactionRow, ParsedTasteEvalRow, TasteScore
from parsing.merge import merge_transactions_with_taste


def _tx(**overrides) -> ParsedMealTransactionRow:
    base = dict(
        eaten_at=dt.datetime(2026, 6, 25, 12, 5, 0),
        department_name="Aa 부문",
        worksite_name="기술캠퍼스",
        company_name="지리산",
        employee_id="E1001",
        company_type="관계사",
        caterer="웰스토리",
        restaurant="SAIT",
        corner_name="한식",
        meal_type=MealType.LUNCH,
        packaging="DINE_IN",
        menu_code_name="한식01",
        menu_display_name="해물잡탕밥",
        receipt_no="100001",
        status="정상",
        is_corrected=False,
    )
    base.update(overrides)
    return ParsedMealTransactionRow(**base)


def _ev(**overrides) -> ParsedTasteEvalRow:
    base = dict(
        eaten_date=dt.date(2026, 6, 25),
        knox_id="E1001",
        meal_type=MealType.LUNCH,
        taste_score=TasteScore.DELICIOUS,
        menu_name="해물잡탕밥",
        comment=None,
    )
    base.update(overrides)
    return ParsedTasteEvalRow(**base)


def test_matching_transaction_gets_taste_score_and_comment():
    merged = merge_transactions_with_taste([_tx()], [_ev(comment="맛있어요")])
    assert len(merged) == 1
    assert merged[0].taste_score == TasteScore.DELICIOUS
    assert merged[0].comment == "맛있어요"
    assert merged[0].menu_name == "해물잡탕밥"


def test_unmatched_transaction_has_no_evaluation():
    merged = merge_transactions_with_taste([_tx(employee_id="E9999")], [_ev()])
    assert merged[0].taste_score is None
    assert merged[0].comment is None


def test_menu_name_mismatch_does_not_match():
    # 같은 사람·같은 날·같은 식사구분이어도 메뉴명이 다르면 다른 끼니로 취급
    merged = merge_transactions_with_taste([_tx(menu_display_name="다른메뉴")], [_ev()])
    assert merged[0].taste_score is None


def test_meal_type_vocabulary_normalized_across_sources():
    # 취식기록="중식", 맛평가="점심" — 둘 다 MealType.LUNCH로 정규화돼 있어야 매칭됨
    merged = merge_transactions_with_taste([_tx(meal_type=MealType.LUNCH)], [_ev(meal_type=MealType.LUNCH)])
    assert merged[0].taste_score is not None


def test_non_normal_status_excluded_by_default():
    merged = merge_transactions_with_taste([_tx(status="취소")], [_ev()])
    assert merged == []


def test_non_normal_status_included_when_flag_off():
    merged = merge_transactions_with_taste([_tx(status="취소")], [_ev()], only_normal_status=False)
    assert len(merged) == 1


def test_multiple_transactions_partial_match():
    transactions = [_tx(employee_id="E1001"), _tx(employee_id="E1002", menu_display_name="파파돈가스")]
    evaluations = [_ev(knox_id="E1001")]
    merged = merge_transactions_with_taste(transactions, evaluations)
    matched = [m for m in merged if m.taste_score is not None]
    assert len(matched) == 1
    assert matched[0].employee_id == "E1001"
