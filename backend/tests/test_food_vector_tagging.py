from app.services.food_vector import FOOD_VECTOR_DIMENSIONS
from app.services.food_vector_tagging import (
    _parse_llm_vector_response,
    tag_food_vector_from_name,
)


def test_tag_food_vector_from_name_matches_known_keywords():
    vector, matched_any = tag_food_vector_from_name("제육볶음")
    assert matched_any is True
    protein_idx = FOOD_VECTOR_DIMENSIONS.index("protein")
    oily_idx = FOOD_VECTOR_DIMENSIONS.index("oily")
    assert vector[protein_idx] > vector[FOOD_VECTOR_DIMENSIONS.index("sour")]
    assert vector[oily_idx] > vector[FOOD_VECTOR_DIMENSIONS.index("sour")]


def test_tag_food_vector_from_name_returns_no_match_for_unknown_menu():
    vector, matched_any = tag_food_vector_from_name("모듬과일")
    assert matched_any is False
    assert len(vector) == len(FOOD_VECTOR_DIMENSIONS)


def test_parse_llm_vector_response_valid():
    response = "spicy: 0.9, sweet: 0.1, salty: 0.1, sour: 0.1, oily: 0.1, protein: 0.2, carb: 0.1, fried: 0.0, soup_based: 0.0, vegetable_ratio: 0.1"
    parsed = _parse_llm_vector_response(response)
    assert parsed is not None
    assert len(parsed) == len(FOOD_VECTOR_DIMENSIONS)
    assert parsed[FOOD_VECTOR_DIMENSIONS.index("spicy")] == 0.9


def test_parse_llm_vector_response_missing_dimension_returns_none():
    response = "spicy: 0.9, sweet: 0.1"
    assert _parse_llm_vector_response(response) is None


def test_parse_llm_vector_response_clamps_out_of_range_values():
    response = ", ".join(f"{dim}: 5.0" for dim in FOOD_VECTOR_DIMENSIONS)
    parsed = _parse_llm_vector_response(response)
    assert parsed is not None
    assert all(v == 1.0 for v in parsed)
