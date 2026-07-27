import datetime as dt

from models import MealType, MenuRole
from parsing.weekly_menu_parser import find_header_row, parse_weekly_menu_grid, split_cell_into_items

MONDAY = dt.date(2026, 7, 20)  # 이 표가 나타내는 주의 월요일 (실제로는 운영자가 지정)


def _sample_grid():
    """병합 셀을 흉내낸 그리드: 같은 조/중/석식·코너가 이어지는 행은 빈 문자열(None)로 표현."""
    return [
        ["구분", "코너", "월", "화", "수", "목", "금", "토", "일"],
        ["중식", "한식", "제육볶음\n계란후라이\n김치", "된장찌개\n생선구이", "", "", "", "", ""],
        [None, None, "", "", "비빔밥\n나물", "", "", "", ""],
        [None, "그린미트", "닭가슴살샐러드", "", "", "", "", "", ""],
        ["석식", "일품", "돈까스/단무지/양배추", "", "", "", "", "", ""],
    ]


def test_find_header_row():
    grid = _sample_grid()
    assert find_header_row(grid) == 0


def test_split_cell_into_items_newline():
    assert split_cell_into_items("제육볶음\n계란후라이\n김치") == ["제육볶음", "계란후라이", "김치"]


def test_split_cell_into_items_slash_delimiter():
    assert split_cell_into_items("돈까스/단무지/양배추") == ["돈까스", "단무지", "양배추"]


def test_split_cell_into_items_empty():
    assert split_cell_into_items("   ") == []


def test_merged_cells_forward_filled_for_meal_type_and_corner():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    # 두 번째 데이터 행(빈 조/중/석식·코너)도 "중식"/"한식"으로 채워졌는지 확인
    wed_rows = [r for r in rows if r.plan_date == MONDAY + dt.timedelta(days=2) and r.corner_name == "한식"]
    assert wed_rows
    assert all(r.meal_type == MealType.LUNCH for r in wed_rows)
    assert {r.menu_name for r in wed_rows} == {"비빔밥", "나물"}


def test_main_dish_is_first_item_side_dishes_are_rest():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    mon_hansik = [
        r for r in rows if r.plan_date == MONDAY and r.corner_name == "한식" and r.meal_type == MealType.LUNCH
    ]
    mains = [r for r in mon_hansik if r.menu_role == MenuRole.MAIN]
    sides = [r for r in mon_hansik if r.menu_role == MenuRole.SIDE]
    assert [m.menu_name for m in mains] == ["제육볶음"]
    assert {s.menu_name for s in sides} == {"계란후라이", "김치"}


def test_green_meat_corner_parsed_like_any_other_corner():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    green = [r for r in rows if r.corner_name == "그린미트"]
    assert len(green) == 1
    assert green[0].menu_name == "닭가슴살샐러드"
    assert green[0].meal_type == MealType.LUNCH  # 코너만 새로 시작, 조/중/석식은 이전 값(중식) 유지


def test_dinner_row_with_slash_separated_items():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    dinner = [r for r in rows if r.meal_type == MealType.DINNER]
    assert {r.menu_name for r in dinner} == {"돈까스", "단무지", "양배추"}
    assert [r.menu_role for r in dinner] == [MenuRole.MAIN, MenuRole.SIDE, MenuRole.SIDE]


def test_empty_day_cells_produce_no_rows():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    thursday = MONDAY + dt.timedelta(days=3)
    assert [r for r in rows if r.plan_date == thursday] == []


def test_source_row_raw_preserved_for_verification():
    rows = parse_weekly_menu_grid(_sample_grid(), MONDAY)
    row = next(r for r in rows if r.menu_name == "제육볶음")
    assert "제육볶음" in row.source_row_raw
    assert "계란후라이" in row.source_row_raw
