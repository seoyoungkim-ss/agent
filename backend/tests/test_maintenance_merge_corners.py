import datetime as dt

from app.maintenance.merge_take_out_corners import merge_take_out_corners
from app.models.enums import Division, MealType
from app.models.logs import MealLog
from app.models.master import CornerMaster, EmployeeMaster
from app.services.master_data import TAKE_OUT_CORNER_NAME, get_or_create_corner


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


def test_merge_take_out_corners_reassigns_meal_log_and_removes_aliases(db_session):
    # get_or_create_corner()는 이제 정규화를 해버리므로, 정규화 배포 "이전"에 이미
    # 갈라져 적재된 상황을 흉내내려면 ORM으로 직접 별칭 코너를 만들어야 한다.
    corner_r = CornerMaster(corner_name="Take Out R")
    corner_m = CornerMaster(corner_name="Take Out M")
    db_session.add_all([corner_r, corner_m])
    db_session.flush()

    log_r = _add_meal_log(db_session, corner_r, "E1")
    log_m = _add_meal_log(db_session, corner_m, "E2")
    db_session.commit()

    reassigned = merge_take_out_corners(db_session)
    assert reassigned == 2

    remaining_corners = db_session.query(CornerMaster).filter(CornerMaster.corner_name.like("Take Out%")).all()
    assert len(remaining_corners) == 1
    assert remaining_corners[0].corner_name == TAKE_OUT_CORNER_NAME

    db_session.refresh(log_r)
    db_session.refresh(log_m)
    assert log_r.corner_id == remaining_corners[0].corner_id
    assert log_m.corner_id == remaining_corners[0].corner_id


def test_merge_take_out_corners_is_idempotent(db_session):
    get_or_create_corner(db_session, "Take Out R")
    db_session.commit()

    first = merge_take_out_corners(db_session)
    second = merge_take_out_corners(db_session)
    assert first == 0  # get_or_create_corner가 이미 정규화해서 별칭이 애초에 안 남음
    assert second == 0
