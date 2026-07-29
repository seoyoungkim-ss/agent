import datetime as dt

from app.maintenance.normalize_employee_ids import normalize_employee_ids
from app.models.enums import Division, MealType
from app.models.logs import MealLog
from app.models.master import CornerMaster, EmployeeMaster


def _add_meal_log(db_session, employee_id: str, corner: CornerMaster) -> MealLog:
    log = MealLog(
        eaten_at=dt.datetime(2026, 6, 25, 12, 0, 0),
        employee_id=employee_id,
        meal_type=MealType.LUNCH,
        corner_id=corner.corner_id,
    )
    db_session.add(log)
    db_session.flush()
    return log


def test_normalize_employee_ids_reassigns_meal_log_and_removes_bad_row(db_session):
    corner = CornerMaster(corner_name="한식")
    db_session.add(corner)
    db_session.flush()

    # get_or_create_employee()는 이제 정규화를 해버리므로, 정규화 배포 "이전"에
    # 이미 ".0"으로 적재된 상황을 흉내내려면 ORM으로 직접 만들어야 한다.
    bad = EmployeeMaster(employee_id="12345678.0", division=Division.HEADQUARTERS, company_name="삼성전자")
    db_session.add(bad)
    db_session.flush()
    log = _add_meal_log(db_session, "12345678.0", corner)
    db_session.commit()

    reassigned = normalize_employee_ids(db_session)
    assert reassigned == 1

    remaining = db_session.query(EmployeeMaster).filter(EmployeeMaster.employee_id.like("12345678%")).all()
    assert len(remaining) == 1
    assert remaining[0].employee_id == "12345678"

    db_session.refresh(log)
    assert log.employee_id == "12345678"


def test_normalize_employee_ids_merges_into_existing_canonical_row(db_session):
    corner = CornerMaster(corner_name="한식")
    db_session.add(corner)
    canonical = EmployeeMaster(employee_id="99998888", division=Division.OTHER)
    bad = EmployeeMaster(employee_id="99998888.0", division=Division.OTHER)
    db_session.add_all([canonical, bad])
    db_session.flush()
    log = _add_meal_log(db_session, "99998888.0", corner)
    db_session.commit()

    reassigned = normalize_employee_ids(db_session)
    assert reassigned == 1

    remaining = db_session.query(EmployeeMaster).filter(EmployeeMaster.employee_id.like("99998888%")).all()
    assert len(remaining) == 1
    assert remaining[0].employee_id == "99998888"

    db_session.refresh(log)
    assert log.employee_id == "99998888"


def test_normalize_employee_ids_is_idempotent(db_session):
    assert normalize_employee_ids(db_session) == 0
    assert normalize_employee_ids(db_session) == 0
