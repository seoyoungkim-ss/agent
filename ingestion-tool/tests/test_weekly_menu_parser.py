import datetime as dt

from models import MealType, MenuRole
from parsing.weekly_menu_parser import find_header_row, parse_weekly_menu_grid, split_cell_into_items

MONDAY = dt.date(2026, 7, 20)  # 이 표가 나타내는 주의 월요일 (실제로는 운영자가 지정)


def _sample_grid():
    """실제 WeeklyMenu.xlsx 레이아웃을 흉내낸 그리드.

    A=조/중/석식, B-C=코너명(2열 병합), D-E=월 ... N-O=토(요일마다 2열 병합,
    일요일 없음). 병합 셀의 오른쪽/이어지는 셀은 xlwings가 None으로 읽는다.

    행2(인덱스0, 한식 블록 시작): 수요일 칸엔 "[한상차림]" 태그, 실제 메인은
    바로 아래 행. 목요일은 "&"로 이어진 메인. 행3: 월요일 메인 아래 재료/
    원산지 주석("(돈육:국내산)", 버려져야 함) + 수요일의 실제 메인("닭갈비").
    행4~5: 부찬들. 행6: 완전 빈 행(블록 안에 섞여 있어도 무해해야 함).
    행7(그린미트, 중식 이어받음): 월요일만 메뉴 있고 나머지 요일은 없음.
    행8~9(일품, 석식): 기본 파싱 범위(중식만) 밖이라 빠져야 함.
    """
    return [
        ["2026년 7월 둘째주 식단표", None, None, None, None, None, None, None, None, None, None, None, None, None, None],
        ["구분", "코너", None, "7/6(월)", None, "7/7(화)", None, "7/8(수)", None, "7/9(목)", None, "7/10(금)", None, "7/11(토)", None],
        ["중식", "한식", None, "제육볶음", None, "된장찌개", None, "[한상차림]", None, "함박스테이크&소스", None, "비빔밥", None, "돈까스", None],
        [None, None, None, "(돈육:국내산)", None, None, None, "닭갈비", None, None, None, None, None, None, None],
        [None, None, None, "김치", None, "깍두기", None, None, None, "피클", None, "나물", None, "단무지", None],
        [None, None, None, "계란후라이", None, None, None, None, None, None, None, None, None, None, None],
        [None] * 15,
        [None, "그린미트", None, "닭가슴살샐러드", None, None, None, None, None, None, None, None, None, None, None],
        ["석식", "일품", None, "돈까스", None, "함박스테이크", None, "카레", None, "우동", None, "김밥", None, "떡볶이", None],
        [None, None, None, "단무지", None, "피클", None, None, None, None, None, None, None, None, None],
    ]


def test_find_header_row_is_second_row():
    assert find_header_row(_sample_grid()) == 1


def test_find_header_row_matches_date_prefixed_weekday_label():
    # 실제 파일은 요일 헤더 셀이 "월" 단독이 아니라 "7/6(월)"처럼 날짜와 같이 들어있음
    grid = [
        [None] * 15,
        ["구분", "코너", None, "7/6(월)", None, "7/7(화)", None, "7/8(수)", None, "7/9(목)", None, "7/10(금)", None, "7/11(토)", None],
    ]
    assert find_header_row(grid) == 1


def test_split_cell_into_items_newline():
    assert split_cell_into_items("제육볶음\n계란후라이\n김치") == ["제육볶음", "계란후라이", "김치"]


def test_split_cell_into_items_slash_delimiter():
    assert split_cell_into_items("돈까스/단무지/양배추") == ["돈까스", "단무지", "양배추"]


def test_split_cell_into_items_empty():
    assert split_cell_into_items("   ") == []


def test_split_cell_into_items_keeps_ampersand_joined_name_whole():
    assert split_cell_into_items("함박스테이크&소스") == ["함박스테이크&소스"]


def test_main_dish_is_block_first_item_side_dishes_are_rest():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    mon_hansik = [r for r in rows if r.plan_date == MONDAY and r.corner_name == "한식"]
    mains = [r for r in mon_hansik if r.menu_role == MenuRole.MAIN]
    sides = [r for r in mon_hansik if r.menu_role == MenuRole.SIDE]
    assert [m.menu_name for m in mains] == ["제육볶음"]
    assert {s.menu_name for s in sides} == {"김치", "계란후라이"}


def test_special_tag_defers_main_to_next_row_in_same_column():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    wed = MONDAY + dt.timedelta(days=2)
    wed_hansik = [r for r in rows if r.plan_date == wed and r.corner_name == "한식"]
    mains = [r for r in wed_hansik if r.menu_role == MenuRole.MAIN]
    assert [m.menu_name for m in mains] == ["닭갈비"]
    assert all(r.menu_name != "[한상차림]" for r in wed_hansik)
    assert "[한상차림]" in wed_hansik[0].source_row_raw  # 감사 목적으로는 원문 보존


def test_ampersand_joined_main_menu_not_split():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    thu = MONDAY + dt.timedelta(days=3)
    thu_hansik = [r for r in rows if r.plan_date == thu and r.corner_name == "한식"]
    mains = [r for r in thu_hansik if r.menu_role == MenuRole.MAIN]
    assert [m.menu_name for m in mains] == ["함박스테이크&소스"]


def test_ingredient_annotation_is_discarded_not_stored_as_menu():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    assert all(r.menu_name != "(돈육:국내산)" for r in rows)
    mon_hansik = [r for r in rows if r.plan_date == MONDAY and r.corner_name == "한식"]
    assert "(돈육:국내산)" in mon_hansik[0].source_row_raw  # 원문 감사 트레일은 유지


def test_merged_corner_and_meal_type_forward_filled_across_rows():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    fri = MONDAY + dt.timedelta(days=4)
    fri_hansik = [r for r in rows if r.plan_date == fri and r.corner_name == "한식"]
    assert fri_hansik
    assert all(r.meal_type == MealType.LUNCH for r in fri_hansik)


def test_new_corner_block_starts_cleanly_and_inherits_meal_type():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    green = [r for r in rows if r.corner_name == "그린미트"]
    assert len(green) == 1
    assert green[0].menu_name == "닭가슴살샐러드"
    assert green[0].meal_type == MealType.LUNCH  # 코너만 새로 시작, 조/중/석식은 이전 값(중식) 유지
    assert green[0].plan_date == MONDAY


def test_blank_separator_row_inside_block_is_harmless():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    sat = MONDAY + dt.timedelta(days=5)
    sat_hansik = [r for r in rows if r.plan_date == sat and r.corner_name == "한식"]
    assert {r.menu_name for r in sat_hansik} == {"돈까스", "단무지"}


def test_no_sunday_column_produces_no_seventh_day_rows():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    sunday = MONDAY + dt.timedelta(days=6)
    assert [r for r in rows if r.plan_date == sunday] == []


def test_dinner_block_excluded_by_default_lunch_only_scope():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    assert all(r.meal_type != MealType.DINNER for r in rows)
    assert all(r.corner_name != "일품" for r in rows)


def test_dinner_block_included_when_scope_widened():
    rows = parse_weekly_menu_grid(
        _sample_grid(), MONDAY, included_meal_types=frozenset({MealType.LUNCH, MealType.DINNER})
    )
    ilpum = [r for r in rows if r.corner_name == "일품"]
    assert ilpum
    assert all(r.meal_type == MealType.DINNER for r in ilpum)
    mon_ilpum_mains = [r for r in ilpum if r.plan_date == MONDAY and r.menu_role == MenuRole.MAIN]
    assert [m.menu_name for m in mon_ilpum_mains] == ["돈까스"]


def test_source_row_raw_preserved_for_verification():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    row = next(r for r in rows if r.menu_name == "제육볶음")
    assert "제육볶음" in row.source_row_raw
    assert "김치" in row.source_row_raw
