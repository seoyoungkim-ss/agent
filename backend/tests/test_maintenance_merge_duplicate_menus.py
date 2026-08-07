"""표기만 다른 메뉴 병합 — 특히 **슬롯 충돌**.

2026-08 실사용: `--apply`가 IntegrityError로 죽었다.

    key (plan_date, corner_id, meal_type, menu_id, menu_role) already exists

같은 슬롯에 두 표기가 모두 편성돼 있으면 `menu_id`를 대표로 옮긴 결과가 기존 행과
완전히 같아져 `uq_weekly_menu_plan_slot_menu_role`을 위반한다. **애초에 병합이
필요한 데이터일수록 이 충돌이 나기 쉽다** — 식단표에 두 표기가 같이 올라간 게
갈라짐의 원인이기 때문이다.
"""

import datetime as dt

from app.maintenance.merge_duplicate_menus import merge_duplicate_menus
from app.models.enums import Division, MealType, MenuRole
from app.models.logs import MealLog, WeeklyMenuPlan
from app.models.master import CornerMaster, EmployeeMaster, MenuMaster
from app.models.stats import MenuPerformanceStats

MONDAY = dt.date(2026, 7, 6)


def _split_menus(db):
    """표기만 다른 두 메뉴 행 — 정규화하면 같은 키가 된다."""
    a = MenuMaster(menu_name="연어파피요트")
    b = MenuMaster(menu_name="연어 파피요트")
    db.add_all([a, b])
    db.flush()
    return a, b


def _corner(db, name="한식"):
    corner = CornerMaster(corner_name=name)
    db.add(corner)
    db.flush()
    return corner


def _plan(db, corner, menu, *, role=MenuRole.MAIN, day=MONDAY):
    row = WeeklyMenuPlan(
        plan_date=day,
        meal_type=MealType.LUNCH,
        corner_id=corner.corner_id,
        menu_id=menu.menu_id,
        menu_role=role,
        is_new_menu=False,
    )
    db.add(row)
    db.flush()
    return row


def test_same_slot_collision_does_not_raise(db_session):
    """신고 재현 — 두 표기가 같은 슬롯·같은 역할에 있으면 예전엔 죽었다."""
    corner = _corner(db_session)
    a, b = _split_menus(db_session)
    _plan(db_session, corner, a)
    _plan(db_session, corner, b)  # 같은 슬롯, 같은 역할 → 옮기면 충돌
    db_session.commit()

    merge_duplicate_menus(db_session, apply=True)

    rows = db_session.query(WeeklyMenuPlan).all()
    assert len(rows) == 1, "충돌한 행이 합쳐지지 않았다"
    assert rows[0].menu_id == a.menu_id


def test_non_colliding_rows_are_remapped_not_deleted(db_session):
    """충돌하지 않는 행은 그대로 대표 메뉴로 옮겨져야 한다 — 편성 이력이 줄면 안 된다."""
    corner = _corner(db_session)
    a, b = _split_menus(db_session)
    _plan(db_session, corner, a, day=MONDAY)
    _plan(db_session, corner, b, day=MONDAY + dt.timedelta(days=1))  # 다른 날
    db_session.commit()

    merge_duplicate_menus(db_session, apply=True)

    rows = db_session.query(WeeklyMenuPlan).order_by(WeeklyMenuPlan.plan_date).all()
    assert len(rows) == 2
    assert {r.menu_id for r in rows} == {a.menu_id}


def test_different_roles_in_one_slot_do_not_collide(db_session):
    """제약 키에 menu_role이 들어 있으므로 메인/부찬은 공존할 수 있다."""
    corner = _corner(db_session)
    a, b = _split_menus(db_session)
    _plan(db_session, corner, a, role=MenuRole.MAIN)
    _plan(db_session, corner, b, role=MenuRole.SIDE)
    db_session.commit()

    merge_duplicate_menus(db_session, apply=True)

    roles = {r.menu_role for r in db_session.query(WeeklyMenuPlan).all()}
    assert roles == {MenuRole.MAIN, MenuRole.SIDE}


def test_meal_log_snapshot_is_repointed_not_orphaned(db_session):
    """⚠️ 삭제되는 식단표 행을 취식기록이 참조 중이면 FK가 막는다.

    NULL로 밀면 과거 취식 이력이 끊긴다(§56.1에서 문제 삼은 그 실수). 살아남는
    행으로 옮겨야 한다.
    """
    corner = _corner(db_session)
    a, b = _split_menus(db_session)
    keeper_plan = _plan(db_session, corner, a)
    doomed_plan = _plan(db_session, corner, b)

    db_session.add(EmployeeMaster(employee_id="E1", division=Division.OTHER))
    db_session.flush()
    log = MealLog(
        eaten_at=dt.datetime(2026, 7, 6, 12, 0),
        employee_id="E1",
        meal_type=MealType.LUNCH,
        corner_id=corner.corner_id,
        menu_id=b.menu_id,
        menu_snapshot_id=doomed_plan.id,
    )
    db_session.add(log)
    db_session.commit()

    merge_duplicate_menus(db_session, apply=True)

    db_session.refresh(log)
    assert log.menu_snapshot_id is not None, "스냅샷 참조가 끊겼다"
    assert log.menu_snapshot_id == keeper_plan.id
    assert log.menu_id == a.menu_id


def test_meal_log_menu_id_is_remapped(db_session):
    """취식기록의 메뉴 참조도 대표로 옮겨져야 매칭이 붙는다."""
    corner = _corner(db_session)
    a, b = _split_menus(db_session)
    db_session.add(EmployeeMaster(employee_id="E1", division=Division.OTHER))
    db_session.flush()
    db_session.add(
        MealLog(
            eaten_at=dt.datetime(2026, 7, 6, 12, 0),
            employee_id="E1",
            meal_type=MealType.LUNCH,
            corner_id=corner.corner_id,
            menu_id=b.menu_id,
        )
    )
    db_session.commit()

    merge_duplicate_menus(db_session, apply=True)

    assert db_session.query(MealLog).one().menu_id == a.menu_id


def test_dry_run_changes_nothing(db_session):
    corner = _corner(db_session)
    a, b = _split_menus(db_session)
    _plan(db_session, corner, a)
    _plan(db_session, corner, b)
    db_session.commit()

    merge_duplicate_menus(db_session, apply=False)

    assert db_session.query(WeeklyMenuPlan).count() == 2
    assert db_session.query(MenuMaster).count() == 2


def test_is_idempotent(db_session):
    corner = _corner(db_session)
    a, b = _split_menus(db_session)
    _plan(db_session, corner, a)
    _plan(db_session, corner, b)
    db_session.commit()

    merge_duplicate_menus(db_session, apply=True)
    assert merge_duplicate_menus(db_session, apply=True) == 0


# ---------------------------------------------------------------------------
# menu_performance_stats 참조 (2026-08 두 번째 신고)
# ---------------------------------------------------------------------------
# "key menu id is still referenced from table menu performance stats"
# FK를 weekly_menu_plan·meal_log만 챙기고 이 테이블을 빠뜨렸다.


def _stats(db, menu, *, start=dt.date(2026, 1, 1), end=dt.date(2026, 6, 30)):
    row = MenuPerformanceStats(
        menu_id=menu.menu_id,
        period_start=start,
        period_end=end,
        adjusted_score=4.0,
        raw_score=4.0,
        evaluation_count=10,
        total_headcount=100,
    )
    db.add(row)
    db.flush()
    return row


def test_performance_stats_do_not_block_the_merge(db_session):
    """신고 재현 — 통계 행이 남아 있으면 메뉴 삭제가 FK로 막혔다."""
    a, b = _split_menus(db_session)
    _stats(db_session, b)
    db_session.commit()

    merge_duplicate_menus(db_session, apply=True)

    assert db_session.query(MenuMaster).filter(MenuMaster.menu_id == b.menu_id).count() == 0


def test_stats_for_the_same_period_would_collide_so_both_are_dropped(db_session):
    """같은 기간 통계가 양쪽에 있으면 옮길 수 없다 — (기간, 메뉴)가 유니크다.

    두 행의 점수는 더할 수 있는 값이 아니라 원본에서 다시 계산해야 하므로,
    대표 것까지 지우고 재계산에 맡긴다.
    """
    a, b = _split_menus(db_session)
    _stats(db_session, a)
    _stats(db_session, b)  # 같은 기간 — 옮기면 유니크 위반
    db_session.commit()

    merge_duplicate_menus(db_session, apply=True)

    assert db_session.query(MenuPerformanceStats).count() == 0, "낡은 통계가 남았다"


def test_merge_stops_with_a_named_table_if_a_new_reference_appears(db_session, monkeypatch):
    """모르는 참조가 생기면 raw IntegrityError 대신 테이블 이름을 알려준다.

    FK 목록을 손으로 관리하다 이번에 놓쳤다. 다음에 테이블이 늘면 스택만 보고
    헤매지 않도록 삭제 직전에 검사한다.
    """
    import app.maintenance.merge_duplicate_menus as mod

    a, b = _split_menus(db_session)
    db_session.commit()
    monkeypatch.setattr(mod, "_remaining_references", lambda db, ids: {"어떤새테이블.menu_id": 3})

    try:
        mod.merge_duplicate_menus(db_session, apply=True)
    except RuntimeError as exc:
        assert "어떤새테이블.menu_id" in str(exc)
    else:
        raise AssertionError("남은 참조를 못 잡았다")
