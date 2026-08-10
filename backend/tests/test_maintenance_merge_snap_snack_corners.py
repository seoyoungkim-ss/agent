import datetime as dt

from app.maintenance.merge_snap_snack_corners import merge_snap_snack_corners
from app.models.enums import Division, MealType
from app.models.logs import MealLog
from app.models.master import CornerMaster, EmployeeMaster
from app.services.master_data import SNAP_SNACK_CORNER_NAME, get_or_create_corner


def _add_meal_log(db_session, corner: CornerMaster, employee_id: str) -> MealLog:
    db_session.add(EmployeeMaster(employee_id=employee_id, division=Division.OTHER))
    db_session.flush()
    log = MealLog(
        eaten_at=dt.datetime(2026, 6, 25, 12, 0, 0),
        employee_id=employee_id,
        meal_type=MealType.LUNCH,
        corner_id=corner.corner_id,
    )
    db_session.add(log)
    db_session.flush()
    return log


def test_merge_snap_snack_corners_reassigns_meal_log_and_removes_aliases(db_session):
    # get_or_create_corner()는 이제 정규화를 해버리므로, 정규화 배포 "이전"에 이미
    # 갈라져 적재된 상황을 흉내내려면 ORM으로 직접 별칭 코너를 만들어야 한다.
    corner_a = CornerMaster(corner_name="스냅스낵")
    corner_b = CornerMaster(corner_name="스냅스넥")
    db_session.add_all([corner_a, corner_b])
    db_session.flush()

    log_a = _add_meal_log(db_session, corner_a, "E1")
    log_b = _add_meal_log(db_session, corner_b, "E2")
    db_session.commit()

    # Take Out과 달리 대표 이름("스냅스낵")이 별칭 집합 자체에 포함돼 있어
    # get_or_create_corner가 새로 만들지 않고 기존 corner_a를 그대로 대표로
    # 쓴다 — 그래서 재배정 대상은 나머지 별칭(corner_b)의 1건뿐이다.
    reassigned = merge_snap_snack_corners(db_session)
    assert reassigned == 1

    remaining_corners = (
        db_session.query(CornerMaster).filter(CornerMaster.corner_name.like("스냅스%")).all()
    )
    assert len(remaining_corners) == 1
    assert remaining_corners[0].corner_name == SNAP_SNACK_CORNER_NAME

    db_session.refresh(log_a)
    db_session.refresh(log_b)
    assert log_a.corner_id == remaining_corners[0].corner_id
    assert log_b.corner_id == remaining_corners[0].corner_id


def test_merge_snap_snack_corners_is_idempotent(db_session):
    get_or_create_corner(db_session, "스냅스낵")
    db_session.commit()

    first = merge_snap_snack_corners(db_session)
    second = merge_snap_snack_corners(db_session)
    assert first == 0  # get_or_create_corner가 이미 정규화해서 별칭이 애초에 안 남음
    assert second == 0
