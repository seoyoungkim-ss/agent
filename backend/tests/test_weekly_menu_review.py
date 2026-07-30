import datetime as dt

from app.models.enums import MenuRole
from app.services.weekly_menu_review import feedback_deadline, group_weekly_menu_rows


def test_feedback_deadline_is_seven_days_before_plan_date():
    assert feedback_deadline(dt.date(2026, 8, 10)) == dt.date(2026, 8, 3)


def test_group_weekly_menu_rows_groups_main_and_sides_by_slot():
    rows = [
        (1, dt.date(2026, 8, 10), 1, "한식", "중식", 100, "제육볶음", MenuRole.MAIN, "규칙기반"),
        (2, dt.date(2026, 8, 10), 1, "한식", "중식", 101, "계란찜", MenuRole.SIDE, "규칙기반"),
        (3, dt.date(2026, 8, 10), 1, "한식", "중식", 102, "김치", MenuRole.SIDE, "규칙기반"),
        (4, dt.date(2026, 8, 11), 2, "일품", "중식", 200, "돈까스", MenuRole.MAIN, "LLM추정"),
    ]
    today = dt.date(2026, 8, 1)

    slots = group_weekly_menu_rows(rows, today=today)

    assert len(slots) == 2
    hansik_slot = next(s for s in slots if s.corner_name == "한식")
    assert hansik_slot.main is not None
    assert hansik_slot.main.menu_name == "제육볶음"
    assert {s.menu_name for s in hansik_slot.sides} == {"계란찜", "김치"}
    assert hansik_slot.feedback_deadline == dt.date(2026, 8, 3)
    assert hansik_slot.is_past_deadline is False  # today(8/1) <= deadline(8/3)

    ilpum_slot = next(s for s in slots if s.corner_name == "일품")
    assert ilpum_slot.main.role_source == "LLM추정"


def test_group_weekly_menu_rows_marks_past_deadline():
    rows = [(1, dt.date(2026, 7, 1), 1, "한식", "중식", 100, "제육볶음", MenuRole.MAIN, "규칙기반")]
    slots = group_weekly_menu_rows(rows, today=dt.date(2026, 8, 1))
    assert slots[0].is_past_deadline is True  # deadline 6/24, today 8/1


def test_group_weekly_menu_rows_keeps_extra_main_in_sides_instead_of_dropping():
    # 관리자가 부찬을 메인으로 고쳤는데 기존 메인을 아직 안 내린 경우 — 두 번째
    # MAIN 항목을 조용히 버리지 않고 sides에 남겨야 한다(데이터 유실 방지).
    rows = [
        (1, dt.date(2026, 8, 10), 1, "한식", "중식", 100, "제육볶음", MenuRole.MAIN, "규칙기반"),
        (2, dt.date(2026, 8, 10), 1, "한식", "중식", 101, "계란찜", MenuRole.MAIN, "관리자수동"),
    ]
    slots = group_weekly_menu_rows(rows, today=dt.date(2026, 8, 1))
    assert slots[0].main.menu_name == "제육볶음"
    assert [s.menu_name for s in slots[0].sides] == ["계란찜"]
