import datetime as dt

from models import MealType, ParsedMealTransactionRow, ParsedTasteEvalRow, TasteScore
from parsing.merge import (
    diagnose_match_failure,
    diagnose_match_failure_by_evaluation,
    merge_transactions_with_taste,
    sample_field_mismatches,
)


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


def test_company_name_carried_through_for_division_classification():
    merged = merge_transactions_with_taste([_tx(company_name="삼성전자")], [])
    assert merged[0].company_name == "삼성전자"


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


def test_employee_mapping_resolves_mismatched_ids():
    # B/C/D사 등은 사번과 Knox ID 체계가 달라 매핑 없이는 매칭 안 됨
    transactions = [_tx(employee_id="88887777")]
    evaluations = [_ev(knox_id="knoxABC")]
    mapping = {"88887777": "knoxABC"}

    unmapped = merge_transactions_with_taste(transactions, evaluations)
    assert unmapped[0].taste_score is None  # 매핑 없으면 미평가로 남음(정상 동작)

    mapped = merge_transactions_with_taste(transactions, evaluations, employee_mapping=mapping)
    assert mapped[0].taste_score is not None


def test_employee_mapping_missing_entry_falls_back_to_employee_id():
    # 매핑 파일에 없는 사번(A사처럼 사번==knox_id인 경우)은 그대로 통과해야 함
    transactions = [_tx(employee_id="E1001")]
    evaluations = [_ev(knox_id="E1001")]
    mapping = {"다른사번": "다른knox"}

    merged = merge_transactions_with_taste(transactions, evaluations, employee_mapping=mapping)
    assert merged[0].taste_score is not None


def test_diagnose_match_failure_all_fields_match():
    d = diagnose_match_failure([_tx()], [_ev()])
    assert d["full_match"] == 1
    assert d["match_without_id"] == 1
    assert d["match_without_date"] == 1
    assert d["match_without_meal_type"] == 1
    assert d["match_without_menu"] == 1


def test_diagnose_match_failure_isolates_id_mismatch():
    # ID만 다르고 나머지(날짜/식사구분/메뉴명)는 같음 — match_without_id만 높아야 함
    transactions = [_tx(employee_id="E9999")]
    evaluations = [_ev(knox_id="E1001")]

    d = diagnose_match_failure(transactions, evaluations)
    assert d["full_match"] == 0
    assert d["match_without_id"] == 1
    assert d["match_without_date"] == 0
    assert d["match_without_meal_type"] == 0
    assert d["match_without_menu"] == 0


def test_diagnose_match_failure_isolates_menu_name_mismatch():
    transactions = [_tx(menu_display_name="다른메뉴")]
    evaluations = [_ev(menu_name="해물잡탕밥")]

    d = diagnose_match_failure(transactions, evaluations)
    assert d["full_match"] == 0
    assert d["match_without_id"] == 0
    assert d["match_without_menu"] == 1


def test_diagnose_match_failure_uses_employee_mapping():
    transactions = [_tx(employee_id="88887777")]
    evaluations = [_ev(knox_id="knoxABC")]
    mapping = {"88887777": "knoxABC"}

    d = diagnose_match_failure(transactions, evaluations, employee_mapping=mapping)
    assert d["full_match"] == 1


def test_diagnose_match_failure_no_matches_anywhere():
    transactions = [_tx(employee_id="E9999", menu_display_name="다른메뉴")]
    evaluations = [_ev(eaten_date=dt.date(2026, 1, 1))]

    d = diagnose_match_failure(transactions, evaluations)
    assert d["full_match"] == 0
    assert d["match_without_id"] == 0
    assert d["match_without_date"] == 0
    assert d["match_without_menu"] == 0


def test_diagnose_match_failure_by_evaluation_all_fields_match():
    d = diagnose_match_failure_by_evaluation([_tx()], [_ev()])
    assert d["total_evaluations"] == 1
    assert d["full_match"] == 1
    assert d["match_without_id"] == 1
    assert d["match_without_date"] == 1
    assert d["match_without_meal_type"] == 1
    assert d["match_without_menu"] == 1


def test_diagnose_match_failure_by_evaluation_isolates_id_mismatch():
    transactions = [_tx(employee_id="E9999")]
    evaluations = [_ev(knox_id="E1001")]

    d = diagnose_match_failure_by_evaluation(transactions, evaluations)
    assert d["full_match"] == 0
    assert d["match_without_id"] == 1
    assert d["match_without_date"] == 0
    assert d["match_without_meal_type"] == 0
    assert d["match_without_menu"] == 0


def test_diagnose_match_failure_by_evaluation_isolates_menu_name_mismatch():
    transactions = [_tx(menu_display_name="다른메뉴")]
    evaluations = [_ev(menu_name="해물잡탕밥")]

    d = diagnose_match_failure_by_evaluation(transactions, evaluations)
    assert d["full_match"] == 0
    assert d["match_without_id"] == 0
    assert d["match_without_menu"] == 1


def test_diagnose_match_failure_by_evaluation_uses_employee_mapping():
    transactions = [_tx(employee_id="88887777")]
    evaluations = [_ev(knox_id="knoxABC")]
    mapping = {"88887777": "knoxABC"}

    d = diagnose_match_failure_by_evaluation(transactions, evaluations, employee_mapping=mapping)
    assert d["full_match"] == 1


def test_diagnose_match_failure_by_evaluation_no_matches_anywhere():
    transactions = [_tx(employee_id="E9999", menu_display_name="다른메뉴")]
    evaluations = [_ev(eaten_date=dt.date(2026, 1, 1))]

    d = diagnose_match_failure_by_evaluation(transactions, evaluations)
    assert d["full_match"] == 0
    assert d["match_without_id"] == 0
    assert d["match_without_date"] == 0
    assert d["match_without_menu"] == 0


def test_diagnose_match_failure_by_evaluation_bounded_by_evaluation_count():
    # 취식기록이 훨씬 많아도(인기메뉴 등으로 인한 부풀림 없이), 맛평가 기준
    # 진단의 모든 카운트는 total_evaluations를 넘지 않아야 한다.
    transactions = [_tx(employee_id=f"E{i}") for i in range(50)]
    evaluations = [_ev(knox_id="E1001")]

    d = diagnose_match_failure_by_evaluation(transactions, evaluations)
    assert d["total_evaluations"] == 1
    for key in ("full_match", "match_without_id", "match_without_date", "match_without_meal_type", "match_without_menu"):
        assert d[key] <= 1


def test_sample_field_mismatches_finds_id_only_difference():
    # 날짜/식사구분/메뉴명은 같은데 ID만 다름 — "id" 샘플에 (맛평가 값, 취식기록 값) 쌍이 잡혀야 함
    transactions = [_tx(employee_id="E9999")]
    evaluations = [_ev(knox_id="E1001")]

    samples = sample_field_mismatches(transactions, evaluations)
    assert samples["id"] == [("E1001", "E9999")]
    assert samples["date"] == []
    assert samples["menu"] == []


def test_sample_field_mismatches_finds_menu_only_difference():
    transactions = [_tx(menu_display_name="다른메뉴")]
    evaluations = [_ev(menu_name="해물잡탕밥")]

    samples = sample_field_mismatches(transactions, evaluations)
    assert samples["menu"] == [("해물잡탕밥", "다른메뉴")]
    assert samples["id"] == []


def test_sample_field_mismatches_finds_date_only_difference():
    transactions = [_tx(eaten_at=dt.datetime(2026, 6, 26, 12, 0, 0))]
    evaluations = [_ev(eaten_date=dt.date(2026, 6, 25))]

    samples = sample_field_mismatches(transactions, evaluations)
    assert samples["date"] == [(dt.date(2026, 6, 25), dt.date(2026, 6, 26))]


def test_sample_field_mismatches_empty_when_fully_matched():
    samples = sample_field_mismatches([_tx()], [_ev()])
    assert samples == {"id": [], "date": [], "menu": []}


def test_sample_field_mismatches_respects_employee_mapping():
    transactions = [_tx(employee_id="88887777")]
    evaluations = [_ev(knox_id="knoxABC")]
    mapping = {"88887777": "knoxABC"}

    # 매핑 적용하면 완전 매칭이라 id 샘플이 비어 있어야 함
    samples = sample_field_mismatches(transactions, evaluations, employee_mapping=mapping)
    assert samples["id"] == []
