from app.services.voe_category import VOE_CATEGORIES, classify_voe_categories


def test_single_category_matched():
    assert classify_voe_categories("오늘 메뉴 진짜 맛있어요") == ["맛"]


def test_multiple_categories_matched():
    result = classify_voe_categories("맛없고 위생도 별로예요")
    assert set(result) == {"맛", "위생"}


def test_no_match_returns_empty_list():
    assert classify_voe_categories("그냥 평범했습니다") == []


def test_service_category_matched():
    assert classify_voe_categories("직원분이 너무 불친절해요") == ["서비스"]


def test_seasoning_category_matched():
    assert classify_voe_categories("국이 너무 싱거워요") == ["간"]


def test_all_categories_are_covered_by_keyword_rules():
    from app.services.voe_category import _CATEGORY_KEYWORDS

    assert set(_CATEGORY_KEYWORDS.keys()) == set(VOE_CATEGORIES)
    assert all(len(kws) > 0 for kws in _CATEGORY_KEYWORDS.values())
