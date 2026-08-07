import datetime as dt

import pytest

from models import MealType, MenuRole
from parsing.weekly_menu_parser import (
    WeeklyMenuParseError,
    find_header_row,
    infer_week_start,
    is_origin_annotation_text,
    parse_weekly_menu_grid,
    split_cell_into_items,
)

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


def test_find_header_row_matches_datetime_valued_header_cells():
    # 날짜서식이 입혀진 셀은 화면엔 "7/6(월)"로 보여도 xlwings가 문자열이
    # 아니라 datetime을 돌려주는 경우가 있음 — str()로 바꾸면 요일 글자가
    # 사라지므로, 요일을 직접 계산해서 인식해야 한다.
    grid = [
        [None] * 15,
        [
            "구분", "코너", None,
            dt.datetime(2026, 7, 6), None,
            dt.datetime(2026, 7, 7), None,
            dt.datetime(2026, 7, 8), None,
            dt.datetime(2026, 7, 9), None,
            dt.datetime(2026, 7, 10), None,
            dt.datetime(2026, 7, 11), None,
        ],
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


def test_split_cell_into_items_strips_trailing_origin_annotation():
    # "(우육:호주산)"이 별도 셀이 아니라 메뉴명 끝에 바로 붙어 들어오는 경우 —
    # 취식기록/맛평가에는 원산지 정보가 없어 매칭이 깨지므로 제거해야 한다.
    assert split_cell_into_items("우삼겹구이(우육:호주산)") == ["우삼겹구이"]


def test_split_cell_into_items_merges_ampersand_fragment_split_by_newline():
    # "제육볶음&미니우동"이 줄바꿈으로 감싸져 "제육볶음\n&미니우동"처럼 들어오면
    # 줄바꿈 분리 때문에 "&미니우동"이 조각난 별도 항목이 되면 안 된다 — 원래
    # 하나의 메인메뉴명("제육볶음&미니우동")으로 다시 이어붙여야 한다.
    assert split_cell_into_items("제육볶음\n&미니우동") == ["제육볶음&미니우동"]
    assert split_cell_into_items("제육볶음\n&미니우동\n김치") == ["제육볶음&미니우동", "김치"]


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


# ---------------------------------------------------------------------------
# 원산지 주석 (2026-08 재작성)
# ---------------------------------------------------------------------------
# ⚠️ 이 케이스 표는 `backend/tests/test_menu_name.py`의 ORIGIN_CASES와 **같은
# 내용이어야 한다.** 두 패키지가 코드를 공유할 수 없어 판정 로직이 복제돼 있고,
# 2026-08까지 실제로 어긋나 있었다(양쪽 다 콜론만 인정해 `(계육-국산)`을 놓쳤다).

# (입력, 통째로 원산지인가, 주석 제거 후 이름)
ORIGIN_CASES = [
    ("(계육-국산)", True, ""),
    ("(오징어-중국산)", True, ""),
    ("(돈육:국내산)", True, ""),
    ("(쌀:국내산, 돈육:국내산)", True, ""),
    ("*돈육:국내산", True, ""),
    ("우삼겹구이(우육:호주산)", False, "우삼겹구이"),
    ("우삼겹구이(우육:호주산, 돈육:국내산)", False, "우삼겹구이"),
    ("오징어(중국산)", False, "오징어"),
    ("계육(국산)", False, "계육"),
    ("(오징어볶음-매운맛)", False, "(오징어볶음-매운맛)"),
    ("김치찌개(얼큰한맛)", False, "김치찌개(얼큰한맛)"),
    ("제육볶음", False, "제육볶음"),
    ("함박스테이크&소스", False, "함박스테이크&소스"),
    # 2026-08: 원산지가 아닌 재료 구성이 섞여도 통째로 주석이다
    ("(햄-계육, 돈육:국내산)", True, ""),
    ("(햄-계육)", True, ""),
    # 2026-08: 7자 원산지를 못 잡아 메뉴가 갈라졌다(연어파피요트 신고)
    ("연어파피요트(연어:노르웨이자연산)", False, "연어파피요트"),
    ("(연어스테이크-노르웨이)", False, "(연어스테이크-노르웨이)"),
    # 2026-08: 원산지 괄호가 문자열 끝이 아니면(뒤에 "&메뉴명"이 더 있으면) 안
    # 떨어지던 버그 — 신고 재현
    ("명란크림파스타(명란:미국산)&베이컨포테이토피자", False, "명란크림파스타&베이컨포테이토피자"),
    # 2026-08: 재료-짝 폴백이 strip 쪽엔 안 붙어 있어서 안 떨어지던 버그 — 신고 재현
    ("햄마늘종볶음(햄-계육, 돈육:국내산)", False, "햄마늘종볶음"),
    # 위 두 버그가 겹친 경우 — 괄호가 두 개
    (
        "명란크림파스타(명란:미국산)&베이컨포테이토피자(계육:국내산)",
        False,
        "명란크림파스타&베이컨포테이토피자",
    ),
]


@pytest.mark.parametrize("raw,is_annotation,_normalized", ORIGIN_CASES)
def test_is_origin_annotation_text(raw, is_annotation, _normalized):
    assert is_origin_annotation_text(raw) is is_annotation


@pytest.mark.parametrize("raw,_is_annotation,normalized", ORIGIN_CASES)
def test_strip_origin_annotation_via_split(raw, _is_annotation, normalized):
    """셀 하나짜리 입력이면 split 결과가 정규화된 이름 하나(또는 없음)여야 한다."""
    items = split_cell_into_items(raw)
    assert items == ([normalized] if normalized else [])


def test_split_does_not_cut_inside_parentheses():
    """괄호 안 쉼표에서 자르면 메인 이름이 `우삼겹구이(우육:호주산`으로 망가진다.

    2026-08 실사용 신고의 가장 파괴적인 경로 — 부찬 오염을 넘어 **메인메뉴명
    자체가 깨져** 취식기록과 영영 매칭되지 않는다.
    """
    assert split_cell_into_items("우삼겹구이(우육:호주산, 돈육:국내산)") == ["우삼겹구이"]


def test_multiline_cell_drops_only_the_annotation_line():
    assert split_cell_into_items("제육볶음\n(돈육:국내산, 고춧가루:중국산)") == ["제육볶음"]


def test_multiple_annotations_in_one_cell_are_all_dropped():
    assert split_cell_into_items("(계육-국산),(오징어-중국산)") == []


def test_normal_menu_items_still_split_on_separators():
    """원산지 판정을 넓히면서 평범한 항목 분리가 망가지면 안 된다."""
    assert split_cell_into_items("돈까스,단무지") == ["돈까스", "단무지"]
    assert split_cell_into_items("제육볶음\n계란후라이") == ["제육볶음", "계란후라이"]
    assert split_cell_into_items("제육볶음\n&미니우동") == ["제육볶음&미니우동"]


# ---------------------------------------------------------------------------
# 주차(week_start) 자동 인식 (2026-08)
# ---------------------------------------------------------------------------
# ⚠️ 위쪽 _sample_grid()를 여기 쓰면 안 된다 — 헤더는 7/6~7/11인데 모듈 상수
# MONDAY는 2026-07-20이라 일부러 어긋나 있다(운영자가 지정하던 시절의 픽스처).
# 추론 테스트는 헤더와 기대값이 반드시 일치해야 하므로 전용 픽스처를 쓴다.

TODAY = dt.date(2026, 8, 6)  # 추론 기준일을 고정해야 테스트가 시간에 안 흔들린다


def _header_grid(day_cells):
    """요일 헤더 행만 있는 최소 그리드 (D열부터 2열씩)."""
    row = ["구분", "코너", None]
    for cell in day_cells:
        row += [cell, None]
    return [[None] * 15, row]


def test_infer_week_start_from_datetime_header_cells():
    """날짜서식 셀은 xlwings가 datetime을 주므로 연도까지 그대로 확정된다."""
    grid = _header_grid([dt.datetime(2026, 7, 6) + dt.timedelta(days=i) for i in range(6)])
    assert infer_week_start(grid, today=TODAY) == dt.date(2026, 7, 6)


def test_infer_week_start_from_text_header_picks_year_by_weekday():
    """"7/6(월)"엔 연도가 없다 — 7/6이 월요일인 해는 2025~2027 중 2026뿐이다."""
    grid = _header_grid(["7/6(월)", "7/7(화)", "7/8(수)", "7/9(목)", "7/10(금)", "7/11(토)"])
    assert infer_week_start(grid, today=TODAY) == dt.date(2026, 7, 6)


def test_infer_week_start_does_not_jump_into_the_future_at_year_end():
    """소급 적재의 연말 함정 — "가장 가까운 해"로 고르면 미래로 찍힌다.

    오늘이 2026-08-06일 때 12/22는 2026-12-22(138일 후)가 2025-12-22(227일 전)보다
    가깝다. 그래서 근접도가 아니라 **요일**로 연도를 정한다(2025-12-22=월,
    2026-12-22=화). 8개월치 소급 적재는 연말을 반드시 넘으므로 실제로 터지는 케이스다.
    """
    grid = _header_grid(
        ["12/22(월)", "12/23(화)", "12/24(수)", "12/25(목)", "12/26(금)", "12/27(토)"]
    )
    assert infer_week_start(grid, today=TODAY) == dt.date(2025, 12, 22)


def test_infer_week_start_skips_years_without_the_date():
    """2/29는 없는 해가 있다 — 그 해를 후보에서 조용히 빼야 한다."""
    grid = _header_grid(
        ["2/28(월)", "2/29(화)", "3/1(수)", "3/2(목)", "3/3(금)", "3/4(토)"]
    )
    assert infer_week_start(grid, today=dt.date(2028, 3, 10)) == dt.date(2028, 2, 28)


def test_infer_week_start_fails_when_header_has_no_dates():
    """요일 글자만 있으면 어느 주인지 알 수 없다 — 지어내지 말고 실패해야 한다."""
    grid = _header_grid(["월", "화", "수", "목", "금", "토"])
    with pytest.raises(WeeklyMenuParseError, match="날짜를 읽지 못해"):
        infer_week_start(grid, today=TODAY)


def test_infer_week_start_fails_when_days_are_not_consecutive():
    """한 칸이 다른 주를 가리키면 레이아웃이 다른 것 — 조용히 넘기면 안 된다.

    7/13도 월요일이라 그 칸만 보면 멀쩡하다. 칸들끼리 교차 검증해야 잡힌다.
    """
    grid = _header_grid(
        ["7/13(월)", "7/7(화)", "7/8(수)", "7/9(목)", "7/10(금)", "7/11(토)"]
    )
    with pytest.raises(WeeklyMenuParseError, match="연속이 아닙니다"):
        infer_week_start(grid, today=TODAY)


def test_infer_week_start_result_drives_parse_dates_end_to_end():
    """추론 → 파싱까지 이어붙였을 때 실제 plan_date가 맞는지."""
    grid = _sample_grid()
    grid[1] = _header_grid(
        ["7/6(월)", "7/7(화)", "7/8(수)", "7/9(목)", "7/10(금)", "7/11(토)"]
    )[1]
    week_start = infer_week_start(grid, today=TODAY)
    rows = parse_weekly_menu_grid(grid, week_start)
    assert min(r.plan_date for r in rows) == dt.date(2026, 7, 6)
    assert max(r.plan_date for r in rows) == dt.date(2026, 7, 11)


# ---------------------------------------------------------------------------
# "&"로 이어진 메인메뉴가 행 경계로 나뉜 경우 (2026-08 신고)
# ---------------------------------------------------------------------------
# 담당자: "메인메뉴가 '&'로 연결된 경우 & 뒤에까지 메인메뉴임".
# 같은 셀 안 줄바꿈은 이미 처리됐지만, 엑셀에서 줄이 다른 **행**으로 나뉘어
# 들어오면 "&소스"가 별도 부찬이 됐다.


def _one_day_grid(day_cells):
    """월요일 칸에만 값이 있는 최소 그리드. day_cells가 행 순서대로 들어간다."""
    header = ["구분", "코너", None, "7/6(월)", None, "7/7(화)", None, "7/8(수)", None,
              "7/9(목)", None, "7/10(금)", None, "7/11(토)", None]
    rows = []
    for i, cell in enumerate(day_cells):
        first = ["중식", "한식", None] if i == 0 else [None, None, None]
        rows.append(first + [cell] + [None] * 11)
    return [[None] * 15, header, *rows]


def _monday_items(grid):
    parsed = parse_weekly_menu_grid(grid, dt.date(2026, 7, 6))
    mon = [r for r in parsed if r.plan_date == dt.date(2026, 7, 6)]
    return [(r.menu_name, r.menu_role.value) for r in mon]


def test_ampersand_fragment_in_next_row_joins_the_main_menu():
    """신고 재현 — `&소스`가 부찬으로 떨어져 나오면 안 된다."""
    assert _monday_items(_one_day_grid(["함박스테이크", "&소스"])) == [("함박스테이크&소스", "메인")]


def test_ampersand_join_does_not_swallow_real_side_dishes():
    """이어붙이기가 뒤따르는 진짜 부찬까지 먹으면 안 된다."""
    assert _monday_items(_one_day_grid(["함박스테이크", "&소스", "김치"])) == [
        ("함박스테이크&소스", "메인"),
        ("김치", "부찬"),
    ]


def test_ampersand_as_first_item_is_left_alone():
    """앞에 붙일 게 없으면 지어내지 않는다."""
    assert _monday_items(_one_day_grid(["&소스"])) == [("&소스", "메인")]


def test_ampersand_still_joins_inside_one_cell():
    """기존 동작(셀 안 줄바꿈)이 깨지지 않아야 한다."""
    assert _monday_items(_one_day_grid(["함박스테이크\n&소스"])) == [("함박스테이크&소스", "메인")]


# ---------------------------------------------------------------------------
# 재료 주석 판정 확대 (2026-08 신고)
# ---------------------------------------------------------------------------
# 담당자: "(햄-계육, 돈육:국내산) 이런 류의 원산지는 중복 볼 때 빼줘".
# 예전엔 괄호 안 **모든** 항목이 원산지여야 주석으로 봐서, `햄-계육`처럼 원산지가
# 아닌 재료 구성이 섞이면 괄호 전체가 유령 부찬으로 들어왔다.


@pytest.mark.parametrize(
    "text",
    [
        "(햄-계육, 돈육:국내산)",  # 신고 케이스 — 원산지와 재료 구성이 섞임
        "(햄-계육)",  # 원산지 없이 재료 구성만
        "(돈육:국내산)",
        "(우육:호주산, 돈육:국내산)",
    ],
)
def test_ingredient_annotation_is_recognized(text):
    assert is_origin_annotation_text(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "(오징어볶음-매운맛)",  # 앞 토큰이 조리법 어미 → 메뉴명이다
        "(연어스테이크-노르웨이)",
        "(비빔밥-곱빼기)",
        "김치찌개(얼큰한맛)",  # 메뉴명 + 주석 혼합은 뒤쪽만 떼는 경로가 담당
        "제육볶음",
    ],
)
def test_real_menu_names_survive_the_wider_rule(text):
    """판정을 넓히면서 정상 메뉴명이 지워지면 데이터가 통째로 사라진다."""
    assert is_origin_annotation_text(text) is False


def test_ingredient_annotation_row_does_not_become_a_side_dish():
    """파싱 전 구간에서 유령 부찬이 안 생기는지."""
    assert _monday_items(_one_day_grid(["제육볶음", "(햄-계육, 돈육:국내산)", "김치"])) == [
        ("제육볶음", "메인"),
        ("김치", "부찬"),
    ]
